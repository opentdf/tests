// Build step for a staged `web` SDK dist directory. Run from that directory
// after `npm install` (stage.sh does both).
//
// 1. Bundles page.js with the installed @opentdf/sdk into bundle.js, an ES
//    module the browser can load with no further resolution. The SDK's own
//    `import` export condition already targets browsers (dist/web), so esbuild
//    only has to resolve and concatenate; no Node polyfills are involved.
// 2. Writes features.json, a static record of what the bundled library
//    reports about itself. `cli.sh supports` answers from this file, so a
//    feature probe never has to launch a browser.
import { writeFile } from 'node:fs/promises';
import { build } from 'esbuild';

await build({
  entryPoints: ['page.js'],
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: 'es2022',
  outfile: 'bundle.js',
  minify: false,
  logLevel: 'warning',
});

const sdk = await import('@opentdf/sdk');
const features = {
  version: sdk.version,
  tdfSpecVersion: sdk.tdfSpecVersion,
  publicKeyAlgorithms: [...(sdk.PUBLIC_KEY_ALGORITHMS ?? [])],
  hasCreateTDF: typeof sdk.OpenTDF?.prototype?.createTDF === 'function',
};
if (!features.version || !sdk.OpenTDF) {
  throw new Error(`@opentdf/sdk is missing version or OpenTDF: ${JSON.stringify(features)}`);
}
await writeFile('features.json', `${JSON.stringify(features, null, 2)}\n`);
console.log(`web driver bundled against @opentdf/sdk ${features.version}`);
