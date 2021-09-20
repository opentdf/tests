const { Command } = require("commander");
const fs = require("fs");
const {
  prepareBrowser,
  uploadFile,
  getCreds
} = require("./utils/oss-encrypt-decrypt-helpers");
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
  process.stderr.write(`completed oss-browser.js with browser-tdf-js`);
};

async function encrypt() {
  const creds = getCreds(program, configs);
  const { page, browser } = await prepareBrowser(program, creds);
  // var file = fs.readFileSync(program.srcFile, { encoding: "utf-8" });
  await uploadFile({
    selector: "#encrypt",
    srcFile: program.srcFile,
    page
  });
  await done(browser);
}

async function decrypt() {
  const creds = getCreds(program, configs);
  const { page, browser } = await prepareBrowser(program, creds);
  await uploadFile({
    selector: "#decrypt",
    srcFile: program.srcFile,
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
  .option("-u, --userId <email>", "User email address or client id")
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
