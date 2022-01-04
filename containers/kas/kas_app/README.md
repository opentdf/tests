# Simple openTDF Key Access Server

This repo constructs a plain vanilla KAS with attribute config examples.

## Use

Create a local copy of this repository in the directory of your choice and navigate into it:

```bash
$ git clone https://github.com/opentdf/backend.git
$ cd containers/kas/kas_app
$ scripts/start
```

To test, use the `scripts/monotest kas/kas_app` command from the monorepo root.

### Run KAS in background

[Docker](https://www.docker.com/get-started) must be installed.

Optionally you can use these steps to start the docker container.

```
# this command reads the Dockerfile to build a docker image called
# "opentdf/kas". The build process copies the local directory into the container
# and installs the dependencies. If there are no changes to the source code
# this step goes fast.
docker build \
  -f Dockerfile \
  -t opentdf/kas .

# this command runs a container
#     -- using the newly minted Docker image "tdf3-kas-oss"
#     -- publishing its internal 8000 port as external TCP port 8000
#     -- and a pseudo-TTY connection to the container's stdin (the -it)

docker run -p "127.0.0.1:4000:8000" opentdf/kas
```

### Develop locally in a virtual environment

[Python 3.6+](https://www.python.org/) must be installed with pipenv.

#### Activate a virtual environment

A KAS server can be run from either dev or test, but only test has the testing scripts installed. Run both in separate windows to simultaneously test and run the server. Command lines assume your working directory is the kas_app subdirectory. Before you start, make sure your pipenv is configured via:

```bash
pipenv pipenv install --dev
```

#### Run the server

To start a KAS on port 4300:

```bash
$ scripts/start 4300
```

The port number is optional; it defaults to 4000 if it is not specified.


# NOTE: OUT OF DATE

TODO: Rewrite this section!

## Configuration

### Required

See the [root README](../../README.md) for instructions on generating keys for EAS and KAS. Keys are required for EAS to operate. Each of the following environment variables must contain a path to the corresponding key:

- KAS_PRIVATE_KEY
  - Private key (SECRET) KAS uses to certify responses.
- KAS_CERTIFICATE
  - Public key KAS clients can use to validate responses.
- KAS_EC_SECP256R1_PRIVATE_KEY
  - (SECRET) private key of curve secp256r1, KAS uses to certify responses.
- KAS_EC_SECP256R1_CERTIFICATE
  - The public key of curve secp256r1, KAS clients can use
   to validate responses.
- EAS_CERTIFICATE
  - The public key used to validate responses from EAS.

EAS host is required for EAS to fetch and check the validity of attributes.
- EAS_HOST
  - EAS host to fetch attributes.
  
### Optional

- SWAGGER_UI

  - "False" or "0" to disable Swagger UI from being served by EAS. Default is to enable Swagger UI and make available on `/ui` path.

### Cross-Origin Resource Sharing (CORS) settings

- WSGI_CORS_HEADERS (Default: "Origin, X-Requested-With, Content-Type, Authorization, X-Session-Id, X-Virtru-Client, X-No-Redirect")
- WSGI_CORS_METHODS (Default: "GET, POST, PUT, PATCH, OPTIONS, DELETE")
- WSGI_CORS_MAX_AGE (Default: 180)
- WSGI_CORS_ORIGIN (Default: "https://localhost")

### Security headers
reference: https://flask.palletsprojects.com/en/master/security/#security-headers

- X-Content-Type-Options 
  - Anti-MIME-Sniffing header
- X-Frame-Options
  - Prevents external sites from embedding your site in an iframe.


## Adding a user to a Block List (DEMO)

First, let's get everything set up:

```sh
scripts/genkeys-if-needed

export MONOLOG_LEVEL=0
export LOGLEVEL=DEBUG

eas/scripts/start
```

Don't forget to alias our servers as `eas.local` and `kas.local`:

```sh
sudo tee -a /etc/hosts > /dev/null << EOF
127.0.0.1    eas.local kas.local kas-gbr.local
EOF
```

Okay, so start the default EAS:

```sh
cd eas
pipenv install --deploy --dev
pipenv run gunicorn \
    --config gunicorn.conf.py \
    --bind :4010 \
    wsgi:app
```

Now let's go with KAS

```sh
export EO_BLOCK_LIST=bob_5678
cd kas_app
pipenv install
pipenv run gunicorn \
    --config gunicorn.conf.py \
    --bind :8000 \
    wsgi:app
```


Okay let's make some TDF3s

#### Option 1: Python
```sh
pip3 install --user tdf3sdk
echo "Hello TDF3" > plain.txt
python3
```


```py
from tdf3sdk import TDF3Client
client = TDF3Client(eas_url="http://eas.local:4010/v1/entity_object", user="Charlie_1234")
client.share_with_users(["Charlie_1234", "tom_1234", "bob_5678"])
client.encrypt_file("plain.txt", "sample.tdf3")
```


Note on my mac (big sur) I also had to
[install pyenv](https://opensource.com/article/19/5/python-3-default-mac)
because of [PLAT-983](https://virtru.atlassian.net/browse/PLAT-983)

```
brew install pyenv
pyenv install 3.9.1
pyenv global 3.9.1
```


#### Option 2: I still can't get python to work dangit

in `

```sh
cd xtest
nvm use 14
npm i
echo "Hello TDF3" > plain.txt
node
```

```js
#!/usr/bin/env node --trace-warnings --unhandled-rejections=strict

const { Client: Tdf3 } = require("tdf3-js");
const fs = require("fs");

const c =
    new Tdf3.Client({
        userId:"Charlie_1234",
        entityObjectEndpoint:"http://eas.local:4010/v1/entity_object",
    });
const ep = new Tdf3.EncryptParamsBuilder().withFileSource("plain.txt").withOffline().withUsersWithAccess(["Charlie_1234", "tom_1234", "bob_5678"]).build();
const os = fs.createWriteStream("sample.tdf3", {flag: "w", encoding: "utf8"});
c.encrypt(ep).then(p => p.pipe(os));
```

Okay, so now you should have a file, `sample.tdf3`, that Charlie owns. Bob is
on the list, but banned the explicit revocation plugin using the EO_BLOCK_LIST
environment variable as above. Compare the outcomes of the following:


Decrypting as Bob:

```js
#!/usr/bin/env node --trace-warnings --unhandled-rejections=strict

const { Client: Tdf3 } = require("tdf3-js");
const fs = require("fs");

const done = () =>
  process.stderr.write(
    `completed cli`
  );
const c =
    new Tdf3.Client({
        userId:"bob_5678",
        entityObjectEndpoint:"https://etheria.local/eas/v1/entity_object",
    });
const dp = new Tdf3.DecryptParamsBuilder().withFileSource("sample.tdf3").build();
const os = fs.createWriteStream("plain-for-charlie.txt", {flag: "w", encoding: "utf8"});
c.decrypt(dp).then(p => {
    p.pipe(os);
    p.on("end", done);
});
```

Decrypting as Charlie:

```js
#!/usr/bin/env node --trace-warnings --unhandled-rejections=strict

const { Client: Tdf3 } = require("tdf3-js");
const fs = require("fs");

const done = () =>
  process.stderr.write(
    `completed cli`
  );
const c =
    new Tdf3.Client({
        userId:"Charlie_1234",
        entityObjectEndpoint:"http://eas.local:4010/v1/entity_object",
        keyRewrapEndpoint: "http://kas.local:8000/rewrap",
        keyUpsertEndpoint: "http://kas.local:8000/upsert",
    });
const dp = new Tdf3.DecryptParamsBuilder().withFileSource("sample.tdf3").build();
const os = fs.createWriteStream("plain-for-charlie.txt", {flag: "w", encoding: "utf8"});
c.decrypt(dp).then(p => {
    p.pipe(os);
    p.on("end", done);
});
```

## Rotating Keys (DEMO)

Okay, so configure local EAS and KAS as described above. From the xtest folder, after running `npm i`, we have a working environment for testing our system. So let's first bring up a local stack and create a tdf.


```shell
export MONOLOG_LEVEL=0
rm -r certs
echo "This is some plain text" > plain.txt
scripts/genkeys-if-needed
docker-compose -f docker-compose.yml up --build
```


```javascript
#!/usr/bin/env node --trace-warnings --unhandled-rejections=strict

const fs = require("fs");
const https = require("https");
https.globalAgent.options.ca = fs.readFileSync('../../etheria/certs/ca.crt');

const { Client: Tdf3 } = require("../../tdf3-js/src");

const c =
    new Tdf3.Client({
        userId:"Charlie_1234",
        entityObjectEndpoint:"https://etheria.local/eas/v1/entity_object",
    });
const ep = new Tdf3.EncryptParamsBuilder().withFileSource("plain.txt").withOffline().build();
const os = fs.createWriteStream("charlie-01.tdf3", {flag: "w", encoding: "utf8"});
c.encrypt(ep).then(p => p.pipe(os));
```

### Changing EAS keys.

This should not cause problems for the workflow using our current clients, as we generally do not cache EAS keys.

1. kill all servers (ctrl+c on the docker-compose thread, or otherwise send SIGTERM)
2. Regenerate the EAS keys:
```
GENKEYS_FOR_APPS=eas scripts/genkey-apps
```
3. restart with the new keys, e.g. `docker-compose up` (Keys are loaded via local volumes)
4. Decrypt still works:

```javascript
#!/usr/bin/env node --trace-warnings --unhandled-rejections=strict

const fs = require("fs");
const https = require("https");
https.globalAgent.options.ca = fs.readFileSync('../../etheria/certs/ca.crt');

const { Client: Tdf3 } = require("../../tdf3-js/src");

const c =
    new Tdf3.Client({
        userId:"Charlie_1234",
        entityObjectEndpoint:"https://etheria.local/eas/v1/entity_object",
    });

const done = () =>
  process.stderr.write(
    `completed cli`
  );

const dp = new Tdf3.DecryptParamsBuilder().withFileSource("charlie-01.tdf3").build();
const os = fs.createWriteStream("charlie-01-plain.txt", {flag: "w", encoding: "utf8"});
c.decrypt(dp).then(p => {
    p.pipe(os);
    p.on("end", done);
});
```

- If we did not kill EAS, the KAS would still have the incorrect EAS key and would fail with a 4xx error.

#### After rotating KAS key naively

1. kill all servers
2. `GENKEYS_FOR_APPS=kas scripts/genkey-apps`
3. Try to decrypt using the above script. This will fail with a `CryptoError` as KAS will be unable to unwrap the key information, as it was stored with the old KAS public key.
4. Try to encrypt. This works since the current EAS default key is generated during startup. This WILL FAIL once the database is made persistent, as the attribute storage will still reference the old key; currently the database is refreshed during the deployment.
