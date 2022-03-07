const { Command } = require("commander");
require('colors');
const {
  prepareBrowser,
  uploadFile,
  getCreds
} = require("./utils/tdf3-encrypt-decrypt-helpers.js");
const program = new Command();

const done = async browser => {
  try {
    await browser.close();
  } finally {
    await browser.close();
  }
  process.stderr.write('completed tdf3-browser.js with browser-tdf-js \n'.green);
};

async function encrypt() {
  const { srcFile } = program.opts();
  const creds = getCreds();
  const { page, browser } = await prepareBrowser(program, creds);

  await uploadFile({
    selector: "#encrypt",
    srcFile,
    page
  });

  await done(browser);
}

async function decrypt() {
  const { srcFile } = program.opts();
  const creds = getCreds();
  const { page, browser } = await prepareBrowser(program, creds);

  await uploadFile({
    selector: "#decrypt",
    srcFile,
    page
  });

  await done(browser);
}

async function metadata() {
  const { srcFile } = program.opts();
  const creds = getCreds();
  const { page, browser } = await prepareBrowser(program, creds);

  await uploadFile({
    selector: "#metadata",
    srcFile,
    page
  });

  await done(browser);
}

async function manifest() {
  const { srcFile } = program.opts();
  const creds = getCreds();
  const { page, browser } = await prepareBrowser(program, creds);

  await uploadFile({
    selector: "#metadata",
    srcFile,
    page
  });

  await done(browser);
}

program
  .option("-i, --srcFile <path>", "input file")
  .option("-o, --dstFile <path>", "output file")

program
  .command("encrypt")
  .option(
    `-m, --mimeType <mimeType>`,
    "Content Type to apply to the file (ignored)"
  )
  .action(encrypt);

program.command("decrypt").action(decrypt);

program.command("metadata").action(metadata);

program.command("manifest").action(manifest);

program.parse(process.argv);