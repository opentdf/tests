# Integration Tests

Integration tests with PKI are complicated. Chrome will prompt for a user to select a certificate.

## Tests

- requestClientTest - test the client api (_expect to fail_)

## Test Locally

To test locally, you must generate a CA and client certificate. The client certificate must be signed by the CA. See [Etheria Readme.md](https://github.com/virtru/etheria#genkey-tools)

On MacOS add auto select certificate for Chromium

```shell
defaults write org.chromium.Chromium AutoSelectCertificateForUrls -array
defaults write org.chromium.Chromium AutoSelectCertificateForUrls -array-add -string '{"pattern":"https://local.virtru.com/*","filter":{}}'
```

Now run the tests

```shell
tools/genkeys-if-needed
docker-compose -f docker-compose.pki.yml up --build --detach 
cd abacus/web
npm i
npm run test-client
```

**Note: Puppeteer headless mode doesn't work with PKI, at this time.**

## Auto Select Certificate Documentation [WIP]

Resources:

- https://groups.google.com/g/robotframework-users/c/IFj7hQxPc2I
- https://github.com/puppeteer/puppeteer/issues/540
- https://www.chromium.org/administrators/policy-list-3#AutoSelectCertificateForUrls
- https://github.com/puppeteer/puppeteer/issues/1319#issuecomment-371503788
- https://github.com/puppeteer/puppeteer/issues/540#issuecomment-394785965

TODO:

- Get OS Version
- Get binary path

const puppeteer = require('puppeteer');
console.log(puppeteer.executablePath())

- Get manifest
MacOS: ./node_modules/puppeteer/.local-chromium/mac-782078/chrome-mac/Chromium.app/Contents/Resources/org.chromium.Chromium.manifest/Contents/Resources/org.chromium.Chromium.manifest
Linux: ??

- Update manifest:
MacOS:
<dict>
			<key>pfm_description</key>
			<string></string>
			<key>pfm_name</key>
			<string>AutoSelectCertificateForUrls</string>
			<key>pfm_subkeys</key>
			<array>
				<dict>
					<key>pfm_type</key>
					<string>string</string>
				</dict>
			</array>
			<key>pfm_targets</key>
			<array>
				<string>{\"pattern\":\"https://local.virtru.com\",\"filter\":{\"ISSUER\":{\"CN\":\"ca.local.virtru.com\"}}}</string>
			</array>
			<key>pfm_title</key>
			<string></string>
			<key>pfm_type</key>
			<string>array</string>
		</dict>

What works:
defaults write org.chromium.Chromium AutoSelectCertificateForUrls -array
defaults write org.chromium.Chromium AutoSelectCertificateForUrls -array-add -string '{"pattern":"https://local.virtru.com/*","filter":{}}'


Linux: ??

[
  "{"pattern":"https://www.example.com","filter":{"ISSUER":{"CN":"certificate issuer name", "L": "certificate issuer location", "O": "certificate issuer org", "OU": "certificate issuer org unit"}, "SUBJECT":{"CN":"certificate subject name", "L": "certificate subject location", "O": "certificate subject org", "OU": "certificate subject org unit"}}}"
]
