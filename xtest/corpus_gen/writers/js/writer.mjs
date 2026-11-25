// Corpus writer for the Web (JS) SDK. Reads a JSON array of WriteJobs and writes
// one TDF per job. See corpus_gen/selfcheck.py for the job shape.
//
//   node corpus_gen/writers/js/writer.mjs <jobs.json>
//
// Needs PLATFORMURL, CLIENTID and CLIENTSECRET (and KCFULLURL, else the OIDC
// issuer is read from the platform's well-known configuration). The SDK is
// imported from the installed dist, SDK_DIST overriding the default location.

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

// The SDK logs progress with console.log; stdout is for the per-job lines.
console.log = console.error;

const here = dirname(fileURLToPath(import.meta.url));
const sdkDir = resolve(
  process.env.SDK_DIST ?? resolve(here, '../../../sdk/js/dist/main/node_modules'),
  '@opentdf/sdk'
);
const sdk = await import(pathToFileURL(resolve(sdkDir, 'dist/web/src/index.js')).href);
const version = JSON.parse(readFileSync(resolve(sdkDir, 'package.json'), 'utf8')).version;

const JOB_FIELDS = [
  'out',
  'plaintext',
  'kas',
  'split',
  'attributes',
  'segment_size',
  'mime_type',
  'encrypted_metadata',
  'assertions',
  'target_mode',
];
const KAS_FIELDS = ['url', 'kid', 'alg'];
const SPLIT_FIELDS = ['kas', 'sid'];
const SHAPE_FIELDS = ['id', 'scope', 'applies_to_state', 'statement'];
const ASSERTION_FIELDS = ['kind', 'alg', 'key_pem', 'x5c', ...SHAPE_FIELDS];
const STATEMENT_FIELDS = ['format', 'schema', 'value'];
const SCOPES = ['tdo', 'payload'];
const STATES = ['encrypted', 'unencrypted'];
// The only spec versions the SDK writes; it would stamp any other string
// into the manifest unchecked.
const TARGET_MODES = ['4.2.2', '4.3.0'];

const isObject = (v) => v !== null && typeof v === 'object' && !Array.isArray(v);

function object(v, what, allowed) {
  if (!isObject(v)) {
    throw new Error(`${what} must be an object`);
  }
  for (const k of Object.keys(v)) {
    if (!allowed.includes(k)) {
      throw new Error(`unknown field "${k}" in ${what}`);
    }
  }
  return v;
}

function str(o, key) {
  const v = o[key];
  if (v === undefined || v === null) {
    return null;
  }
  if (typeof v !== 'string') {
    throw new Error(`${key} must be a string`);
  }
  return v;
}

function requireStr(o, key) {
  const v = str(o, key);
  if (v === null) {
    throw new Error(`missing ${key}`);
  }
  return v;
}

function array(o, key) {
  const v = o[key];
  if (v === undefined || v === null) {
    return [];
  }
  if (!Array.isArray(v)) {
    throw new Error(`${key} must be an array`);
  }
  return v;
}

function integer(v, key) {
  if (!Number.isSafeInteger(v)) {
    throw new Error(`${key} must be an integer`);
  }
  return v;
}

function nonEmpty(o, key, what) {
  const v = requireStr(o, key);
  if (v === '') {
    throw new Error(`${what} ${key} must not be empty`);
  }
  return v;
}

/** Applies the optional id, scope, applies_to_state and statement. */
function handlingShape(a, cfg) {
  if (str(a, 'id') !== null) {
    cfg.id = nonEmpty(a, 'id', 'assertion');
  }
  const scope = str(a, 'scope');
  if (scope !== null) {
    if (!SCOPES.includes(scope)) {
      throw new Error(`scope "${scope}" not one of ${SCOPES.join(', ')}`);
    }
    cfg.scope = scope;
  }
  const state = str(a, 'applies_to_state');
  if (state !== null) {
    if (!STATES.includes(state)) {
      throw new Error(`applies_to_state "${state}" not one of ${STATES.join(', ')}`);
    }
    cfg.appliesToState = state;
  }
  if (a.statement !== undefined && a.statement !== null) {
    const s = object(a.statement, 'statement', STATEMENT_FIELDS);
    cfg.statement = {
      format: nonEmpty(s, 'format', 'statement'),
      schema: nonEmpty(s, 'schema', 'statement'),
      value: nonEmpty(s, 'value', 'statement'),
    };
  }
}

/** Returns null for system-metadata, which has its own option. */
function assertionConfig(a) {
  const kind = requireStr(a, 'kind');
  if (kind === 'system-metadata') {
    for (const k of SHAPE_FIELDS) {
      if (a[k] !== undefined && a[k] !== null) {
        throw new Error(`system-metadata takes no ${k}; the SDK builds it`);
      }
    }
    return null;
  }
  if (kind !== 'handling') {
    throw new Error(`unknown assertion kind "${kind}"`);
  }
  if (array(a, 'x5c').length > 0) {
    throw new Error('x5c assertions are not supported by the JS writer');
  }
  const alg = requireStr(a, 'alg');
  const keyPem = requireStr(a, 'key_pem');
  const cfg = {
    id: `handling-${alg.toLowerCase()}`,
    type: 'handling',
    scope: 'tdo',
    appliesToState: 'encrypted',
    statement: {
      format: 'json',
      schema: 'urn:corpus:handling',
      value: '{"handling":"corpus"}',
    },
  };
  handlingShape(a, cfg);
  switch (alg) {
    case 'HS256':
      cfg.signingKey = { alg, key: new TextEncoder().encode(keyPem) };
      break;
    case 'RS256':
      if (!keyPem.includes('BEGIN PRIVATE KEY')) {
        throw new Error('key_pem must be PKCS#8 (BEGIN PRIVATE KEY)');
      }
      cfg.signingKey = { alg, key: keyPem };
      break;
    default:
      throw new Error(`unsupported handling alg "${alg}"`);
  }
  return cfg;
}

/**
 * Maps kas/split onto the SDK's split plan, which takes explicit kid and sid.
 * The SDK fetches each KAS's key for the requested algorithm and never selects
 * by kid, so the manifest is checked against the job afterwards (see check()).
 * Several KAS need an explicit split; an empty sid shares the key between KAOs.
 */
function kasPlan(job) {
  const kas = array(job, 'kas').map((e) => {
    const k = object(e, 'kas entry', KAS_FIELDS);
    return { url: requireStr(k, 'url'), kid: str(k, 'kid'), alg: str(k, 'alg') };
  });
  if (kas.length === 0) {
    throw new Error('need kas or attributes');
  }
  for (const k of kas) {
    if (k.alg !== null && !sdk.isPublicKeyAlgorithm(k.alg)) {
      throw new Error(
        `JS SDK ${version} cannot write wrapping algorithm "${k.alg}" (supported: ${sdk.PUBLIC_KEY_ALGORITHMS.join(', ')})`
      );
    }
  }
  // One algorithm applies to every KAO.
  const algs = new Set(kas.map((k) => k.alg).filter((a) => a !== null));
  if (algs.size > 1) {
    throw new Error(`JS SDK writes one wrapping algorithm per TDF; got ${[...algs].join(', ')}`);
  }
  const rawSplit = array(job, 'split');
  if (rawSplit.length === 0 && kas.length > 1) {
    throw new Error('several kas need an explicit split');
  }
  let order = kas.map((k, i) => ({ k, sid: '', i }));
  if (rawSplit.length > 0) {
    if (rawSplit.length !== kas.length) {
      throw new Error('split must name every kas exactly once');
    }
    const seen = new Set();
    order = rawSplit.map((e) => {
      const s = object(e, 'split entry', SPLIT_FIELDS);
      if (s.kas === undefined || s.kas === null) {
        throw new Error('split entry missing kas');
      }
      const idx = integer(s.kas, 'split kas');
      if (idx < 0 || idx >= kas.length || seen.has(idx)) {
        throw new Error('split must name every kas exactly once');
      }
      seen.add(idx);
      return { k: kas[idx], sid: str(s, 'sid') ?? '', i: idx };
    });
  }
  return {
    algorithm: algs.size === 1 ? [...algs][0] : undefined,
    expected: order.map(({ k, sid }) => ({ ...k, sid })),
    splitPlan: order.map(({ k, sid }) => ({ kas: k.url, kid: k.kid ?? undefined, sid })),
  };
}

/** Builds the SDK's encrypt params and the KAOs the manifest must contain. */
async function params(job, source) {
  const p = { source };
  let expected = [];
  const attrs = array(job, 'attributes');
  if (attrs.length > 0) {
    if (!attrs.every((a) => typeof a === 'string')) {
      throw new Error('attributes must be strings');
    }
    p.autoconfigure = true;
    p.scope = { attributes: attrs, dissem: [] };
  } else {
    const plan = kasPlan(job);
    p.autoconfigure = false;
    p.splitPlan = plan.splitPlan;
    p.wrappingKeyAlgorithm = plan.algorithm;
    expected = plan.expected;
  }

  const seg = job.segment_size;
  if (seg !== undefined && seg !== null) {
    // The SDK refuses non-positive or fractional sizes and clamps nothing else.
    if (!Number.isSafeInteger(seg) || seg <= 0) {
      throw new Error(`segment_size ${seg} must be a positive integer`);
    }
    p.windowSize = seg;
  }
  const mime = str(job, 'mime_type');
  if (mime !== null) {
    // The SDK omits an empty MIME type from the manifest without a word.
    if (mime === '') {
      throw new Error('mime_type must not be empty');
    }
    p.mimeType = mime;
  }
  const meta = str(job, 'encrypted_metadata');
  if (meta !== null) {
    // A blank value would read back the same as none.
    if (meta.trim() === '') {
      throw new Error('encrypted_metadata must not be blank');
    }
    p.metadata = meta;
  }
  const mode = str(job, 'target_mode');
  if (mode !== null) {
    if (!TARGET_MODES.includes(mode)) {
      throw new Error(`target_mode "${mode}" not one of ${TARGET_MODES.join(', ')}`);
    }
    p.tdfSpecVersion = mode;
  }

  const cfgs = [];
  const ids = new Set();
  for (const e of array(job, 'assertions')) {
    const cfg = assertionConfig(object(e, 'assertion', ASSERTION_FIELDS));
    const id = cfg === null ? 'system-metadata' : cfg.id;
    if (ids.has(id)) {
      throw new Error(`duplicate assertion id "${id}"`);
    }
    ids.add(id);
    if (cfg === null) {
      p.systemMetadataAssertion = true;
    } else {
      cfgs.push(cfg);
    }
  }
  if (cfgs.length > 0) {
    p.assertionConfigs = cfgs;
  }
  return { p, expected };
}

const KAO_TYPE = (alg) => {
  if (alg.startsWith('rsa:')) {
    return 'wrapped';
  }
  return alg.startsWith('ec:') ? 'ec-wrapped' : 'mlkem-wrapped';
};

/** Fails when the SDK wrote KAOs other than the ones the job asked for. */
function check(manifest, expected) {
  if (expected.length === 0) {
    return;
  }
  const kaos = manifest.encryptionInformation.keyAccess;
  if (kaos.length !== expected.length) {
    throw new Error(`manifest has ${kaos.length} KAOs, job asked for ${expected.length}`);
  }
  expected.forEach((want, i) => {
    const got = kaos[i];
    const mismatch = (what, w, g) => {
      throw new Error(`KAO ${i}: ${what} is ${JSON.stringify(g)}, job asked for ${JSON.stringify(w)}`);
    };
    if (got.url !== want.url) mismatch('url', want.url, got.url);
    if (want.kid !== null && got.kid !== want.kid) mismatch('kid', want.kid, got.kid);
    if (want.alg !== null && got.type !== KAO_TYPE(want.alg)) {
      mismatch('type', KAO_TYPE(want.alg), got.type);
    }
    if ((got.sid ?? '') !== want.sid) mismatch('sid', want.sid, got.sid);
  });
}

async function write(client, job) {
  const plain = readFileSync(requireStr(job, 'plaintext'));
  const source = new Blob([plain]).stream();
  const { p, expected } = await params(job, source);
  const stream = await client.tdf3Client.encrypt(p);
  const bytes = await stream.toBuffer();
  check(stream.manifest, expected);
  const out = requireStr(job, 'out');
  mkdirSync(dirname(resolve(out)), { recursive: true });
  writeFileSync(out, bytes);
}

async function oidcOrigin(platform) {
  if (process.env.KCFULLURL) {
    return process.env.KCFULLURL;
  }
  const res = await fetch(`${platform}/.well-known/opentdf-configuration`);
  const issuer = (await res.json())?.idp?.issuer;
  if (!issuer) {
    throw new Error('set KCFULLURL: platform configuration names no OIDC issuer');
  }
  return issuer;
}

async function run(path) {
  const jobs = JSON.parse(readFileSync(path, 'utf8'));
  if (!Array.isArray(jobs)) {
    throw new Error(`parse ${path}: expected a JSON array`);
  }
  // Strict decode of every job up front, as the other writers do.
  for (const j of jobs) {
    object(j, 'job', JOB_FIELDS);
  }

  const platform = process.env.PLATFORMURL;
  const clientId = process.env.CLIENTID;
  const clientSecret = process.env.CLIENTSECRET;
  if (!platform || !clientId || !clientSecret) {
    throw new Error('PLATFORMURL, CLIENTID and CLIENTSECRET must be set');
  }
  const authProvider = await sdk.AuthProviders.clientSecretAuthProvider({
    clientId,
    clientSecret,
    exchange: 'client',
    oidcOrigin: await oidcOrigin(platform),
  });
  const client = new sdk.OpenTDF({
    authProvider,
    disableDPoP: true,
    policyEndpoint: platform,
    platformUrl: platform,
  });

  let failed = false;
  for (const job of jobs) {
    const out = typeof job.out === 'string' ? job.out : '';
    try {
      await write(client, job);
    } catch (e) {
      console.error(`job ${out}: ${e instanceof Error ? e.message : e}`);
      failed = true;
      continue;
    }
    process.stdout.write(`${JSON.stringify({ out, sdk: 'js', version })}\n`);
  }
  client.close();
  return failed ? 1 : 0;
}

if (process.argv.length !== 3) {
  console.error('usage: writer.mjs <jobs.json>');
  process.exit(2);
}
let code;
try {
  code = await run(process.argv[2]);
} catch (e) {
  console.error(e instanceof Error ? e.message : e);
  code = 1;
}
// Pipe writes are async on POSIX: exit only once the queued records are flushed.
process.stdout.write('', () => process.exit(code));
