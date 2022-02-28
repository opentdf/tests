const puppeteer = require("puppeteer");
const resolve = require("path").resolve;

function getCreds(program, configs) {
  const { clientOptions: clientOpts, userId, dstFile } = program.opts()

  const stageName = clientOpts;
  if (!stageName || !configs[stageName]) {
    console.error(`Must specify a valid stage, not [${stageName}]`);
    return {};
  }
  const clientOptions = {
    ...configs[stageName],
    email: process.env.VIRTRU_SDK_EMAIL
    // TODO: Set up local eas client for inbox testing.
  };
  if (userId) {
    clientOptions.userId = userId;
    clientOptions.email = userId;
  }
  clientOptions.dstFile = dstFile;
  console.log(`Constructing Client: ${JSON.stringify(clientOptions, null, 2)}`);
  return clientOptions;
}

async function prepareBrowser(program, creds) {
  const { dstFile } = program.opts()

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
  const page = await browser.newPage();
  await page.goto("file://" + resolve(`${__dirname}/../test-page-tdf3.html`));

  const distArr = dstFile.split("/");
  distArr.pop();
  const distFolder = distArr.join("/") + "/";

  await page.evaluate(creds => {
    window.creds = creds;
  }, creds);

  await page._client.send("Page.setDownloadBehavior", {
    behavior: "allow",
    downloadPath: resolve(distFolder)
  });
  await page.waitForSelector("input[type=file]");

  return { page, browser };
}

async function uploadFile({ selector, srcFile, page }) {
  const decryptUploadHandle = await page.waitForSelector(selector);
  await decryptUploadHandle.uploadFile(srcFile);
  await page.waitForTimeout(2000);
}

module.exports = { prepareBrowser, uploadFile, getCreds };