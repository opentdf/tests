[![CI Status](https://github.com/opentdf/tdf3-js/actions/workflows/build.yaml/badge.svg)](https://github.com/opentdf/tdf3-js/actions/workflows/build.yaml)

# tdf3-js

A JavaScript client library that can be used to encrypt and decypt files using the TDF3
specification.

## Install & Build

First install all packages required:

`npm ci`

Build:

`npm run build`. The built file can be found in `/build`

Note: If running tests, the build is run automatically.

## Running Tests

1. Download, and run a KAS (Key Access Server): `npm run setup`
1. Start the KAS: `npm start`
1. Build tdf3-js: `npm run build`
1. Then: `npm test`

Note: Step 1 grabs `master` branch of the kas. If you'd like to get a different branch do the
following:

`BRANCH=<branch name> npm run setup.`

To terminate the running kas: `npm stop`

## Example

For a good starting point on how to implement tdf3-js on your own, please see the
[walkthrough](https://developer.virtru.com/docs/how-to-create-a-tdf3-enabled-web-app).

## Methods

### create()

Creates a new instance of TDF.

```js
const tdfInstance = TDF.create();
```

### setProtocol(protocol)

Set the protocol to be used in either encryption or decryption steps.

```js
tdfInstance.setProtocol('zipstream');
```

#### protocol

Type: `String`

Currently only `'zip'` and `'zipstream'` are implemented. `'zipstream'` should be used when reading
from/writing to a stream.

### setPrivateKey(privateKey)

Sets the private key onto the TDF instance to be used in either the encryption or decryption steps.

```js
tdfInstance.setPrivateKey(privateKey);
```

#### privateKey

Type: `String`

The PEM-encoded private key as a string.

### setPublicKey(publicKey)

Sets the public key onto the TDF instance to be used in either the encryption or decryption steps.

```js
tdfInstance.setPublicKey(publicKey);
```

#### publicKey

Type: `String`

The PEM-encoded public key as a string.

### setEncryption(encryptionObject)

Set the encryption object onto the TDF instance.

```js
tdfInstance.setEncryption(encryptionObject);
```

#### encryptionObject.type

Type: `String`

The type of encryption, currently the only option is `split` to represent key splitting

#### encryptionObject.cipher

Type: `String`

The type of cipher to use for encryption. Available options are `'aes-256-gcm'` and `'aes-256-cbc'`.

### addKeyAccess(keyAccessObject)

Adds a [Key Access Object](https://developer.virtru.com/docs/keyaccessobject) to a TDF instance.

```js
tdfInstance.addKeyAccess(keyAccessObject);
```

### setPolicy(policyObject)

Sets the [Policy Object](https://developer.virtru.com/docs/policy-object) on a TDF instance.

```js
tdfInstance.setPolicy(policyObject);
```

### setEntity(entityObject)

Set the [Entity Object](https://developer.virtru.com/docs/entityobject) on a TDF instance.

```js
tdfInstance.setEntity(entityObject);
```

### setDefaultSegmentSize(segmentSize)

Sets the default size of each segment, in bytes, onto a TDF instance.

```js
tdfInstance.setDefaultSegmentSize(segmentSize);
```

#### segmentSize

Type: `Integer`

Default is set to `1024 * 1024` if one is not provided.

### setIntegrityAlgorithm(integrityAlgorithm, segmentIntegrityAlgorithm [optional])

Sets the integrity algorithm and segment integrity algorithms onto a TDF instance.

```js
tdfInstance.setIntegrityAlgorithm(integrityAlgorithm, segmentIntegrityAlgorithm);
```

#### integrityAlgorithm

Type: `String`

The type of algorithm used to create the root signature, found in the manifest
[integrityInformation](https://developer.virtru.com/docs/manifestjson#section-encryptioninformationintegrityinformation).
Available options are `hs256`.

#### segmentIntegrityAlgorithm

Type: `String`

The type of algorithm used to creat segment signatures. This parameter is optional, and if one is
not provided the `integrityAlgorithm` will be used. Available options are `gmac`.

### addContentStream(contentStream)

Sets a content stream on a TDF instance. Used during encryption when the library needs to read from
a content stream to encrypt stream chunks, eventually to be written as an encrypted file.

```js
tdfInstance.addContentStream(contentStream);
```

#### contentStream

The current implementation of the tdf3-js uses [Node streams](https://nodejs.org/api/stream.html).
For example, you can create a readStream that allows tdf3-js to read from a file source:

```js
const contentStream = fs.createReadStream(_my_file_loc, { encoding: 'binary' });
```

If you are working on a browser-only solution, tdf3-js offers a mock stream that provides a custom
in-memory stream that mimicks Node streams.

#### fileData

Type: `Byte`

The file's data, read from a file upload, for example:

```js
const reader = new FileReader();
reader.onload = (e) => {
  const filedata = reader.result;
  //do something with the filedata
};
```

This value can also be set to `null`, as would be the case for a writeStream (no data present upon
creation).

#### isEncryptOperation

Type: `Boolean`

A boolean that describes whether this stream is used for an encryption or decryption operation. This
is used by the mock stream in lieu of having separate streams (e.g., `createReadStream`,
`createWriteStream`)

### write()

Writes the encrypted content to memory, which can then be saved using any non-streaming method

```js
const result = await tdfInstance.write();

fs.writeFileSync(_my_filename_, result.binary.asBuffer(), { encoding: 'binary', flag: 'w' });
```

### writeStream(writeStream)

Writes the encrypted content to a write stream provided.

```js
await tdfInstance.writeStream(writeStream);
```

#### writeStream

Type: `Node stream` or `MockStream`

The stream can be used to write to a file location, or in-memory.

### readStream(chunker, outputStream)

Reads the content given a `utils.chunker` object and writes to an `outputStream`, for example a
file.

#### url

Type: `String`

The URL of the remote resource from which tdf3-js will read data.

#### outputStream

Type: `Node stream` or `MockStream`

The stream can be used to write to a file location, or in-memory.

### generatePolicyUuid()

Creates a unique identifier for a policy object. Returns a String.

```js
const uuid = await TDF.generatePolicyUuid();
```

### generateKeyPair()

Uses tdf3-js's built-in crypto services to generate a public and private key pair. Returns an object
with `privateKey` and `publicKey` properties.

```js
const keyPair = await TDF.generateKeyPair();
const privateKey = keyPair.privateKey;
const publicKey = keyPair.publicKey;
```

#### kasURL

Type: `String`

The URL of the KAS public key endpoint, for example: `http://localhost:4000/kas_public_key`

#### loadTDFStream(url)

Loads a TDF stream by its remote url, placing the manifest JSON and encrypted payload in memory

```js
await tdfInstance.loadTDFStream(url);
```

#### loadTDF(tdfPath)

Loads a TDF file by its filename string

```js
await tdfInstance.loadTDF(tdfPath);
```

#### sync

Performs a 'syncing' of the symmetric wrapped key and Policy Object. For `remote` Key Access types,
this is performed automatically on encryption.

```js
await tdfInstance.sync();
```
