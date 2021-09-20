// jest-puppeteer.config.js

module.exports = {
  launch: {
    slowMo: 10,
    defaultViewport: null,
    // PKI currently doesn't work with headless mode
    headless: false,
    ignoreHTTPSErrors: true,
    // --no-sandbox Disables the sandbox for all process types that are normally sandboxed.
    //               Meant to be used as a browser-level switch for testing purposes only.
    // --disable-web-security Don't enforce the same-origin policy. (Used by people testing their sites.)
    args: ['--no-sandbox', '--disable-web-security', '--auto-open-devtools-for-tabs'],
  },
};
