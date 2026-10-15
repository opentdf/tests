#!/usr/bin/env node
// Node half of the xtest `web` SDK backend: drives @opentdf/sdk inside a
// headless browser.
//
// Usage: node driver.mjs <encrypt|decrypt> <src-file> <dst-file>
//
// Configuration comes from the environment, exactly as for the other cli.sh
// shims: PLATFORMURL, KASURL, KCFULLURL, CLIENTID, CLIENTSECRET and the
// XT_WITH_* variables (see cli.sh). Driver-only knobs:
//
//   XT_WEB_BROWSER  chromium (default) | firefox | webkit
//   XT_WEB_HEADED   non-empty to show the browser window
//   XT_WEB_DEBUG    non-empty to echo every page console message
//
// What happens:
//   1. A localhost HTTP server starts on an ephemeral port. It serves the page
//      (index.html + bundle.js), reverse-proxies the OIDC provider under
//      /__kc/, and accepts the output under /sink/<token>.
//   2. The browser opens the page; the input is attached to <input type=file>
//      with setInputFiles, which passes the path rather than the bytes.
//   3. page.js runs the encrypt/decrypt and POSTs the output stream back in
//      bounded, offset-tagged chunks, which the sink writes to <dst-file>
//      (or discards, for /dev/null).
import { randomBytes } from 'node:crypto';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { open, readFile, unlink } from 'node:fs/promises';
import http from 'node:http';
import https from 'node:https';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium, firefox, webkit } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const KC_PREFIX = '/__kc';
const env = process.env;
const debug = !!env.XT_WEB_DEBUG;

class UsageError extends Error {}

/**
 * Set the exit status without process.exit(): on macOS stdout/stderr pipes
 * are asynchronous, and exiting outright can drop the error text the xtest
 * assertions grep for. A short unref'd timer covers any handle left open.
 */
function finish(code, message) {
  if (message) {
    console.error(message);
  }
  process.exitCode = code;
  setTimeout(() => process.exit(code), 5000).unref();
}

const isTrue = (v) => v === 'true';

/** A path to a JSON file, or JSON inline -- the XT_WITH_ASSERTIONS contract. */
function fileOrJson(value, what) {
  if (existsSync(value) && statSync(value).isFile()) {
    console.log(`${what} are a file: ${path.resolve(value)}`);
    return readFileSync(value, 'utf8');
  }
  try {
    JSON.parse(value);
  } catch {
    throw new UsageError(`Invalid or missing ${what} file: ${value}`);
  }
  console.log(`${what} are plain json`);
  return value;
}

function attributesFrom(value) {
  let text = value;
  if (existsSync(value) && statSync(value).isFile()) {
    console.log(`Attributes are a file: ${path.resolve(value)}`);
    text = readFileSync(value, 'utf8');
  }
  return text
    .split(/[,\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** Translate the shim environment into the job page.js runs. */
function jobFor(op) {
  for (const name of ['KASURL', 'KCFULLURL', 'PLATFORMURL']) {
    if (!env[name]) {
      throw new UsageError(`${name} is not set; source xtest/test.env`);
    }
  }
  // Rejected rather than ignored: a silently dropped option is a test that
  // passes without exercising what it claims to.
  if (env.XT_WITH_DPOP) {
    throw new UsageError('XT_WITH_DPOP is not supported by the web driver');
  }
  if (isTrue(env.XT_WITH_ECDSA_BINDING)) {
    throw new UsageError('XT_WITH_ECDSA_BINDING is not supported by the web driver');
  }
  if (isTrue(env.XT_WITH_PLAINTEXT_POLICY)) {
    throw new UsageError('XT_WITH_PLAINTEXT_POLICY is not supported by the web driver');
  }

  const job = {
    op,
    clientId: env.CLIENTID || 'opentdf',
    clientSecret: env.CLIENTSECRET || 'secret',
    kasEndpoint: env.KASURL,
    platformUrl: env.PLATFORMURL.replace(/\/+$/, ''),
  };
  const ecwrap = isTrue(env.XT_WITH_ECWRAP);
  if (op === 'encrypt') {
    job.autoconfigure = true;
    if (env.XT_WITH_ATTRIBUTES) {
      job.attributes = attributesFrom(env.XT_WITH_ATTRIBUTES);
      console.log(`Attributes are: ${job.attributes.join(',')}`);
    }
    if (env.XT_WITH_ASSERTIONS) {
      job.assertions = fileOrJson(env.XT_WITH_ASSERTIONS, 'Assertions');
    }
    if (env.XT_WITH_MIME_TYPE) {
      job.mimeType = env.XT_WITH_MIME_TYPE;
    }
    if (env.XT_WITH_TARGET_MODE) {
      job.tdfSpecVersion = env.XT_WITH_TARGET_MODE;
    }
    if (ecwrap) {
      job.wrappingKeyAlgorithm = 'ec:secp256r1';
    }
  } else {
    if (env.XT_WITH_ASSERTION_VERIFICATION_KEYS) {
      const keys = env.XT_WITH_ASSERTION_VERIFICATION_KEYS;
      if (!(existsSync(keys) && statSync(keys).isFile())) {
        throw new UsageError(`Invalid or missing verification keys file: ${keys}`);
      }
      console.log(`Verification keys are a file: ${path.resolve(keys)}`);
      job.assertionVerificationKeys = readFileSync(keys, 'utf8');
    }
    if (env.XT_WITH_VERIFY_ASSERTIONS === 'false') {
      job.noVerify = true;
    }
    if (ecwrap) {
      job.wrappingKeyAlgorithm = 'ec:secp256r1';
    }
    // tdfs.py sets XT_WITH_KAS_ALLOWLIST; the older shims read
    // XT_WITH_KAS_ALLOW_LIST. Accept both.
    const allow = env.XT_WITH_KAS_ALLOWLIST || env.XT_WITH_KAS_ALLOW_LIST;
    if (allow) {
      job.allowList = allow.split(',').filter(Boolean);
    }
    if (isTrue(env.XT_WITH_IGNORE_KAS_ALLOWLIST)) {
      job.ignoreAllowList = true;
    }
  }
  return job;
}

/**
 * Forward a request to `target` (a URL origin), rewriting Host to match.
 *
 * The upstream URL is assembled from parts rather than resolved, and its
 * origin re-checked, so a request path like `//elsewhere/` cannot redirect
 * the proxy to a host other than the IdP.
 */
function reverseProxy(req, res, target, pathname, search) {
  const url = new URL(target);
  url.pathname = pathname;
  url.search = search;
  if (url.origin !== new URL(target).origin) {
    res.writeHead(400, { 'content-type': 'text/plain' }).end('bad proxy path');
    return;
  }
  const headers = { ...req.headers, host: url.host };
  delete headers.connection;
  const transport = url.protocol === 'https:' ? https : http;
  const upstream = transport.request(
    url,
    { method: req.method, headers },
    (ures) => {
      res.writeHead(ures.statusCode ?? 502, ures.headers);
      ures.pipe(res);
    }
  );
  upstream.on('error', (e) => {
    console.error(`proxy ${req.method} ${url} failed: ${e.message}`);
    if (!res.headersSent) {
      res.writeHead(502, { 'content-type': 'text/plain' });
    }
    res.end(`proxy error: ${e.message}`);
  });
  req.pipe(upstream);
}

/**
 * Write side of the output channel. Chunks arrive tagged with their offset and
 * are written positionally, so concurrent POSTs may land in any order.
 */
class Sink {
  constructor(dst) {
    this.dst = dst;
    this.discard = dst === '/dev/null';
    this.received = 0;
    this.closed = false;
    this.fh = undefined;
  }

  /** Open lazily, once, even when the first chunks arrive concurrently. */
  file() {
    this.opening ??= open(this.dst, 'w').then((fh) => (this.fh = fh));
    return this.opening;
  }

  async handle(offset, req) {
    if (this.closed) {
      throw new Error('sink already closed');
    }
    const fh = this.discard ? undefined : await this.file();
    let pos = offset;
    for await (const chunk of req) {
      if (fh) {
        let written = 0;
        while (written < chunk.length) {
          const { bytesWritten } = await fh.write(
            chunk,
            written,
            chunk.length - written,
            pos + written
          );
          written += bytesWritten;
        }
      }
      pos += chunk.length;
      this.received += chunk.length;
    }
  }

  async close(length) {
    if (length !== this.received) {
      throw new Error(`sink received ${this.received} bytes, page reported ${length}`);
    }
    if (!this.discard) {
      // An empty output still has to produce a file.
      const fh = await this.file();
      await fh.close();
      this.fh = undefined;
    }
    this.closed = true;
  }

  /** Remove a partial output so a failed run never leaves plausible plaintext. */
  async abort() {
    await this.opening?.catch(() => {});
    if (this.fh) {
      await this.fh.close().catch(() => {});
      this.fh = undefined;
    }
    if (!this.discard && !this.closed) {
      await unlink(this.dst).catch(() => {});
    }
  }
}

async function startServer(sink, kcOrigin) {
  const token = randomBytes(16).toString('hex');
  const sinkPath = `/sink/${token}`;
  const html = await readFile(path.join(HERE, 'index.html'));
  const bundle = await readFile(path.join(HERE, 'bundle.js'));

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url ?? '/', 'http://127.0.0.1');
    try {
      if (url.pathname.startsWith(`${KC_PREFIX}/`)) {
        reverseProxy(req, res, kcOrigin, url.pathname.slice(KC_PREFIX.length), url.search);
        return;
      }
      if (req.method === 'POST' && url.pathname === sinkPath) {
        const offset = Number(url.searchParams.get('offset'));
        if (!Number.isSafeInteger(offset) || offset < 0) {
          res.writeHead(400).end('bad offset');
          return;
        }
        await sink.handle(offset, req);
        res.writeHead(204).end();
        return;
      }
      if (req.method === 'POST' && url.pathname === `${sinkPath}/close`) {
        await sink.close(Number(url.searchParams.get('length')));
        res.writeHead(204).end();
        return;
      }
      if (req.method === 'GET' && url.pathname === '/') {
        res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' }).end(html);
        return;
      }
      if (req.method === 'GET' && url.pathname === '/bundle.js') {
        res.writeHead(200, { 'content-type': 'text/javascript; charset=utf-8' }).end(bundle);
        return;
      }
      res.writeHead(404).end();
    } catch (e) {
      console.error(`server error on ${req.method} ${url.pathname}: ${e?.stack ?? e}`);
      if (!res.headersSent) {
        res.writeHead(500, { 'content-type': 'text/plain' });
      }
      res.end(String(e?.message ?? e));
    }
  });
  // A multi-GiB run is one long series of short requests; none of them should
  // be cut off by Node's default per-request timeouts.
  server.requestTimeout = 0;
  server.headersTimeout = 0;
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  const { port } = server.address();
  return { server, origin: `http://127.0.0.1:${port}`, sinkPath };
}

async function main() {
  const [op, src, dst] = process.argv.slice(2);
  if (!['encrypt', 'decrypt'].includes(op) || !src || !dst) {
    throw new UsageError('Usage: driver.mjs <encrypt|decrypt> <src-file> <dst-file>');
  }
  if (!existsSync(src)) {
    throw new UsageError(`input file not found: ${src}`);
  }
  const job = jobFor(op);
  const engines = { chromium, firefox, webkit };
  const engineName = env.XT_WEB_BROWSER || 'chromium';
  const engine = engines[engineName];
  if (!engine) {
    throw new UsageError(`XT_WEB_BROWSER must be one of ${Object.keys(engines).join(', ')}`);
  }

  const kc = new URL(env.KCFULLURL);
  const sink = new Sink(dst);
  const { server, origin, sinkPath } = await startServer(sink, kc.origin);
  job.oidcOrigin = `${origin}${KC_PREFIX}${kc.pathname.replace(/\/+$/, '')}`;
  job.sinkUrl = `${origin}${sinkPath}`;

  console.log(
    `web ${op} [${src}] -> [${dst}] in ${engineName}; platform ${job.platformUrl}, ` +
      `kas ${job.kasEndpoint}, oidc ${env.KCFULLURL} via ${origin}${KC_PREFIX}, ` +
      `client ${job.clientId}:***`
  );

  const browser = await engine.launch({ headless: !env.XT_WEB_HEADED });
  let ok = false;
  try {
    const page = await (await browser.newContext()).newPage();
    page.on('console', (m) => {
      const t = m.type();
      if (debug || t === 'error' || t === 'warning') {
        console.error(`[page ${t}] ${m.text()}`);
      }
    });
    page.on('pageerror', (e) => console.error(`[page uncaught] ${e.stack ?? e}`));
    await page.goto(`${origin}/`);
    await page.waitForFunction(() => window.xtestReady === true);
    await page.setInputFiles('#input', path.resolve(src));
    const result = await page.evaluate((j) => window.xtest.run(j), job);
    console.log(`browser sees a ${result.inputBytes}-byte input`);
    if (!result.ok) {
      console.error(`web ${op} failed:\n${result.error}`);
      return 1;
    }
    ok = true;
    console.log(`web ${op} wrote ${result.bytes} bytes`);
    return 0;
  } finally {
    if (!ok) {
      await sink.abort();
    }
    await browser.close().catch(() => {});
    server.closeAllConnections();
    server.close();
  }
}

main().then(
  (code) => finish(code),
  (e) => {
    if (e instanceof UsageError) {
      finish(2, e.message);
    } else {
      finish(1, `web driver error: ${e?.stack ?? e}`);
    }
  }
);
