const { Command } = require("commander");
const colors = require('colors');
const fs = require("fs");
const {
  prepareBrowser,
  uploadFile,
  getCreds
} = require("./utils/tdf3-encrypt-decrypt-helpers.js");
const program = new Command();

const configs = JSON.parse(
  fs.readFileSync("config-oss.json", { encoding: "utf-8" })
);

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
  // const creds = getCreds(program, configs);

  const creds = {
    clientId: "tdf-client",
    organizationName: 'tdf',
    kasEndpoint: 'http://localhost:8000',
    clientSecret: '123-456',
    virtruOIDCEndpoint: 'http://localhost:65432/keycloak/',
  };

  const { page, browser } = await prepareBrowser(program, creds);
  // var file = fs.readFileSync(program.srcFile, { encoding: "utf-8" });
  await uploadFile({
    selector: "#encrypt",
    srcFile,
    page
  });

  await done(browser);
}

async function decrypt() {
  const { srcFile } = program.opts();
  // const creds = getCreds(program, configs);

  const creds = {
    clientId: "tdf-client",
    organizationName: 'tdf',
    kasEndpoint: 'http://localhost:8000',
    clientSecret: '123-456',
    virtruOIDCEndpoint: 'http://localhost:65432/keycloak/',
  };

  const { page, browser } = await prepareBrowser(program, creds);
  await uploadFile({
    selector: "#decrypt",
    srcFile,
    page
  });
  await done(browser);
}

async function metadata() {
  const creds = getCreds(program, configs);
  const { page, browser } = await prepareBrowser(program, creds);
  await uploadFile({
    selector: "#metadata",
    srcFile: program.srcFile,
    page
  });
  await done(browser);
}

async function manifest() {
  const creds = getCreds(program, configs);
  const { page, browser } = await prepareBrowser(program, creds);
  await uploadFile({
    selector: "#metadata",
    srcFile: program.srcFile,
    page
  });
  await done(browser);
}

const pretty_keys = o => `${Object.keys(o).join(" | ")}`;

program
  .option("-i, --srcFile <path>", "input file")
  .option("-o, --dstFile <path>", "output file")
  .requiredOption(
    `-s, --clientOptions <stage name>`,
    `${pretty_keys(configs)}`
  );

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