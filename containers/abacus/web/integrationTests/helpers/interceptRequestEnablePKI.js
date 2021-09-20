/**
 * This script will intercept the remote requests and call them internally to bypass the complication
 * around automating Chromium and PKI.
 *
 * Request interception: https://github.com/puppeteer/puppeteer/issues/1319#issuecomment-371503788
 */
const { URL } = require('url');
const https = require('https');
const config = require('./getRootConfig');

const {
  certs: { caCert, clientCert, clientKey },
} = config;

const asyncRequest = ({ options }) => {
  return new Promise((resolve, reject) => {
    console.log('request');
    const req = https.request(options, (res) => {
      console.log('request', res)
      let body = '';
      res.on('data', (chunk) => {
        body += chunk;
      });
      res.on('end', () => {
        resolve({
          body,
          headers: res.headers,
          statusCode: res.statusCode,
        });
      });
    });
    req.on('error', reject);
    req.end();
  });
};

async function interceptRequestEnablePKI(page) {
  // Enable Request Interception
  await page.setRequestInterception(true);

  page.on('request', async (interceptedRequest) => {
    const { hostname, pathname, search } = new URL(interceptedRequest.url());
    const method = interceptedRequest.method();
    const headers = interceptedRequest.headers();
    const body = interceptedRequest.postData();

    // TODO remove this and use the CA cert
    process.env.NODE_TLS_REJECT_UNAUTHORIZED = 0;

    // Forward the request
    try {
      const options = {
        hostname,
        path: pathname + search,
        method,
        headers,
        body,
        ca: caCert,
        cert: clientCert,
        key: clientKey,
      };
      options.agent = new https.Agent(options);

      console.log(`Intercept request (${method} ${pathname}${search})...`);
      const res = await asyncRequest(options);
      console.log(`Intercept request (${method} ${pathname}${search}) result`, res);

      interceptedRequest.respond({
        status: res.statusCode,
        contentType: res.headers['content-type'],
        headers: res.headers,
        body: res.body,
      });
    } catch (e) {
      console.log(`ERROR: Intercept request (${method} ${pathname}${search}) result`, e);
      console.error(e);
      return interceptedRequest.abort(e);
    }
  });
}

module.exports = interceptRequestEnablePKI;
