// Browser half of the xtest `web` SDK backend.
//
// Bundled by build.mjs (esbuild, platform=browser) together with the
// @opentdf/sdk version under test, and served to headless Chromium by
// driver.mjs. Everything here runs inside the page, so it sees the same
// globals, Blob/File semantics, fetch, CORS and WebCrypto that a web app does.
//
// driver.mjs calls `window.xtest.run(job)` through page.evaluate. The input
// file reaches us through <input type=file id=input> (Playwright's
// setInputFiles hands the browser the path, so nothing is copied); the output
// leaves through chunked POSTs to a sink served by driver.mjs. xtest/README.md
// ("The `web` flavour") explains why the output does not use a download.
import { AuthProviders, OpenTDF, version, tdfSpecVersion } from '@opentdf/sdk';

const asError = (e) => (e instanceof Error ? e : new Error(String(e)));

function safeJson(v) {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

/** Flatten an error and its cause chain to text the xtest assertions can grep. */
function describe(e) {
  const lines = [];
  let cur = e;
  for (let depth = 0; cur && depth < 8; depth++) {
    const err = asError(cur);
    const head = `${err.name}: ${err.message}`;
    // V8 stacks already start with the head line; Gecko and WebKit stacks don't.
    const stack = err.stack?.startsWith(head) ? err.stack.slice(head.length + 1) : err.stack;
    lines.push(`${depth ? 'caused by: ' : ''}${head}`);
    // Fields the SDK hangs on its errors -- requiredObligations on a 403, for
    // one -- which Node's console.error(err) prints for the js CLI.
    for (const [k, v] of Object.entries(err)) {
      if (k !== 'cause' && k !== 'name') {
        lines.push(`  ${k}: ${safeJson(v)}`);
      }
    }
    if (stack) {
      lines.push(stack);
    }
    cur = err.cause;
  }
  return lines.join('\n');
}

/**
 * Libraries before 0.10.0 (web-sdk #835) want RS256 assertion keys as
 * CryptoKeys; their CLI imported the PEM with jose. Later ones take the PEM.
 */
const RS256_NEEDS_CRYPTOKEY = (() => {
  const [major, minor] = String(version).split('.').map(Number);
  return major === 0 && minor < 10;
})();

async function importRs256Pem(pem) {
  const der = Uint8Array.from(
    atob(pem.replace(/-----(BEGIN|END) [A-Z ]+-----/g, '').replace(/\s+/g, '')),
    (c) => c.charCodeAt(0)
  );
  const alg = { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' };
  if (pem.includes('PRIVATE KEY')) {
    return crypto.subtle.importKey('pkcs8', der, alg, true, ['sign']);
  }
  return crypto.subtle.importKey('spki', der, alg, true, ['verify']);
}

/** Same conversion the Node CLI applies to assertion keys read from JSON. */
async function correctAssertionKey({ alg, key }) {
  if (alg === 'HS256') {
    if (typeof key !== 'string') {
      throw new Error('HS256 key must be a string');
    }
    return new TextEncoder().encode(key);
  }
  if (alg === 'RS256') {
    if (typeof key !== 'string') {
      throw new Error('RS256 key must be a PEM string');
    }
    return RS256_NEEDS_CRYPTOKEY ? importRs256Pem(key) : key;
  }
  throw new Error(`Unsupported signing key algorithm: ${alg}`);
}

async function assertionConfigs(raw) {
  if (!raw) {
    return undefined;
  }
  const parsed = JSON.parse(raw);
  if (!parsed) {
    return [];
  }
  const list = Array.isArray(parsed) ? parsed : [parsed];
  for (const a of list) {
    if (a.signingKey) {
      a.signingKey.key = await correctAssertionKey(a.signingKey);
    }
  }
  return list;
}

async function assertionVerificationKeys(raw) {
  if (!raw) {
    return undefined;
  }
  const u = JSON.parse(raw);
  if (!u || typeof u !== 'object') {
    throw new Error('Invalid input: assertion verification keys must be an object');
  }
  if (!(u.Keys && typeof u.Keys === 'object')) {
    if (u.keys && typeof u.keys === 'object') {
      u.Keys = u.keys;
    } else {
      throw new Error('Invalid input: invalid structure of assertionVerificationKeys');
    }
  }
  for (const name of Object.keys(u.Keys)) {
    u.Keys[name].key = await correctAssertionKey(u.Keys[name]);
  }
  return u;
}

/**
 * Pipe `stream` to the driver's sink as a series of POSTs.
 *
 * Each POST carries its byte offset, so the sink can write it positionally and
 * the requests need not land in order. At most `maxInFlight` are outstanding,
 * and the reader is not pulled while that many are, so memory stays bounded
 * by roughly maxInFlight * chunkBytes no matter how large the output is. This
 * works the same in every engine, unlike a download (which WebKit buffers
 * whole and which took a Firefox CI runner down at 4 GiB, DSPX-5084).
 */
async function sinkStream(stream, sinkUrl, { maxInFlight = 4, chunkBytes = 4 << 20 } = {}) {
  const reader = stream.getReader();
  const inFlight = new Set();
  let failure;
  let offset = 0;
  let pending = [];
  let pendingBytes = 0;

  const post = async (body) => {
    while (inFlight.size >= maxInFlight) {
      await Promise.race(inFlight);
    }
    if (failure) {
      throw failure;
    }
    const at = offset;
    offset += body.byteLength;
    const p = fetch(`${sinkUrl}?offset=${at}`, { method: 'POST', body })
      .then(async (r) => {
        if (!r.ok) {
          throw new Error(`sink rejected ${body.byteLength} bytes at ${at}: ${r.status} ${await r.text()}`);
        }
      })
      .catch((e) => {
        failure ??= asError(e);
      })
      .finally(() => inFlight.delete(p));
    inFlight.add(p);
  };

  const flush = async () => {
    if (!pendingBytes) {
      return;
    }
    let body;
    if (pending.length === 1) {
      body = pending[0];
    } else {
      body = new Uint8Array(pendingBytes);
      let o = 0;
      for (const c of pending) {
        body.set(c, o);
        o += c.byteLength;
      }
    }
    pending = [];
    pendingBytes = 0;
    await post(body);
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      if (!value?.byteLength) {
        continue;
      }
      pending.push(value);
      pendingBytes += value.byteLength;
      if (pendingBytes >= chunkBytes) {
        await flush();
      }
    }
    await flush();
    await Promise.all(inFlight);
  } catch (e) {
    await reader.cancel(e).catch(() => {});
    await Promise.allSettled(inFlight);
    throw e;
  }
  if (failure) {
    throw failure;
  }
  const r = await fetch(`${sinkUrl}/close?length=${offset}`, { method: 'POST' });
  if (!r.ok) {
    throw new Error(`sink close failed: ${r.status} ${await r.text()}`);
  }
  return offset;
}

async function authProvider(job) {
  const provider = await AuthProviders.clientSecretAuthProvider({
    clientId: job.clientId,
    clientSecret: job.clientSecret,
    oidcOrigin: job.oidcOrigin,
    exchange: 'client',
  });
  // Fetch the token up front, as the Node CLI does, so an IdP or proxy
  // problem fails here with its own message rather than inside a KAS call.
  await provider.oidcAuth?.get?.();
  console.debug('obtained access token');
  return provider;
}

function inputFile() {
  const input = document.getElementById('input');
  const file = input?.files?.[0];
  if (!file) {
    throw new Error('no input file was attached to #input');
  }
  return file;
}

async function encrypt(job, client) {
  const opts = {
    source: { type: 'file-browser', location: inputFile() },
    autoconfigure: !!job.autoconfigure,
  };
  if (job.attributes?.length) {
    opts.attributes = job.attributes;
  }
  if (job.mimeType) {
    opts.mimeType = job.mimeType;
  }
  if (job.wrappingKeyAlgorithm) {
    opts.wrappingKeyAlgorithm = job.wrappingKeyAlgorithm;
  }
  if (job.tdfSpecVersion) {
    opts.tdfSpecVersion = job.tdfSpecVersion;
  }
  const configs = await assertionConfigs(job.assertions);
  if (configs) {
    opts.assertionConfigs = configs;
  }
  // createTDF is the current name; older releases only have createZTDF.
  const create = client.createTDF ?? client.createZTDF;
  return create.call(client, opts);
}

async function decrypt(job, client) {
  const opts = {
    source: { type: 'file-browser', location: inputFile() },
    concurrencyLimit: 100,
  };
  if (job.noVerify) {
    opts.noVerify = true;
  }
  if (job.wrappingKeyAlgorithm) {
    opts.wrappingKeyAlgorithm = job.wrappingKeyAlgorithm;
  }
  const keys = await assertionVerificationKeys(job.assertionVerificationKeys);
  if (keys) {
    opts.assertionVerificationKeys = keys;
  }
  return client.read(opts);
}

async function run(job) {
  const inputBytes = inputFile().size;
  try {
    const client = new OpenTDF({
      authProvider: await authProvider(job),
      defaultCreateOptions: { defaultKASEndpoint: job.kasEndpoint },
      defaultReadOptions: {
        allowedKASEndpoints: job.allowList,
        ignoreAllowlist: !!job.ignoreAllowList,
        noVerify: !!job.noVerify,
      },
      disableDPoP: true,
      policyEndpoint: job.platformUrl,
      platformUrl: job.platformUrl,
    });
    try {
      const out = job.op === 'encrypt' ? await encrypt(job, client) : await decrypt(job, client);
      const bytes = await sinkStream(out, job.sinkUrl, job.sink);
      return { ok: true, inputBytes, bytes };
    } finally {
      client.close?.();
    }
  } catch (e) {
    return { ok: false, inputBytes, error: describe(e) };
  }
}

window.xtest = { run, version, tdfSpecVersion };
window.xtestReady = true;
