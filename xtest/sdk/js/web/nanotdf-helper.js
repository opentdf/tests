const { Command } = require("commander");
const fs = require("fs");
const program = new Command();
const puppeteer = require("puppeteer");
const resolve = require("path").resolve;
const { getCreds } = require("./utils/oss-encrypt-decrypt-helpers");

const configs = JSON.parse(
  fs.readFileSync("config-oss.json", { encoding: "utf-8" })
);
const done = async browser => {
  try {
    await browser.close();
  } finally {
    await browser.close();
  }
  process.stderr.write(`completed nano.js with nanojs`);
};

async function prepareBrowser(program, creds) {
  const browser = await puppeteer.launch({
    slowMo: 10,
    defaultViewport: null,
    headless: true,
    ignoreHTTPSErrors: true,
    // --no-sandbox Disables the sandbox for all process types that are normally sandboxed.
    //               Meant to be used as a browser-level switch for testing purposes only.
    // --disable-web-security Don't enforce the same-origin policy. (Used by people testing their sites.)
    args: ["--no-sandbox", "--disable-web-security"]
  });
  console.log("ntdf: browser launched");
  const page = await browser.newPage();
  console.log("ntdf: browser newPage succeeded");
  page
    .on("console", message =>
      console.log(
        `${message
          .type()
          .substr(0, 3)
          .toUpperCase()} ${message.text()}`
      )
    )
    .on("pageerror", ({ message }) => console.log(message));

  await page.goto(
    "file://" + resolve(`${__dirname}/../browser/testpage-nanotdf.html`)
  );
  console.log("ntdf: browser goto testpage");
  const distArr = program.dstFile.split("/");
  distArr.pop();
  const distFolder = distArr.join("/") + "/";

  await page.evaluate(creds => {
    window.creds = creds;
  }, creds);
  console.log("ntdf: browser creds set");
  await page._client.send("Page.setDownloadBehavior", {
    behavior: "allow",
    downloadPath: resolve(distFolder)
  });
  console.log("ntdf: browser download behavior set");
  await page.waitForSelector("input[type=file]");

  return { page, browser };
}

async function uploadFile({ selector, srcFile, page }) {
  const decryptUploadHandle = await page.waitForSelector(selector);
  await decryptUploadHandle.uploadFile(srcFile);
  console.log("ntdf: upload handler marked done");
  await page.waitForTimeout(2000);
}

async function decrypt() {
  const creds = getCreds(program, configs);
  const { page, browser } = await prepareBrowser(program, creds);
  console.log("ntdf: browser prepped");
  await uploadFile({
    selector: "#decrypt",
    srcFile: program.srcFile,
    page
  });
  console.log("ntdf: browser uploaded");
  await page.waitForSelector("#download_link_decrypted[download]");
  console.log("ntdf: download available");
  await done(browser);
  console.log("ntdf: browser done");
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
program.command("decrypt").action(decrypt);
program.parse(process.argv);
