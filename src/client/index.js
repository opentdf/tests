import { v4 } from 'uuid';
import { put } from 'axios';
import { ZipReader, streamToBuffer, inBrowser } from '../utils';
import { fromBuffer, fromDataSource } from '../utils/chunkers';
import { base64 } from '../encodings';
import TDF from '../tdf';
import { PlaintextStream } from './tdf-stream';
import { TDFCiphertextStream } from './tdf-cipher-text-stream';
import { AuthProvider, EAS, HttpRequest, NoAuthProvider } from './auth';

import { DEFAULT_SEGMENT_SIZE, DecryptParamsBuilder, EncryptParamsBuilder } from './builders';

const GLOBAL_BYTE_LIMIT = 64 * 1000 * 1000 * 1000; // 64 GB, see WS-9363.
const HTML_BYTE_LIMIT = 100 * 1000 * 1000; // 100 MB, see WS-9476.

// No default config for now. Delegate to Virtru wrapper for endpoints.
const defaultClientConfig = {};

const uploadBinaryToS3 = async function (stream, uploadUrl, fileSize) {
  try {
    if (inBrowser()) {
      /* Buffer the stream in a browser context, stream browser uploads are unsupported
         without a createPresignedPost url or via the aws-sdk using getFederationToken */
      stream = await streamToBuffer(stream);
    }

    const res = await put(uploadUrl, stream, {
      headers: {
        'Content-Length': fileSize,
        'content-type': 'application/zip',
        'cache-control': 'no-store',
      },
      maxContentLength: Infinity,
      maxBodyLength: Infinity,
      body: stream,
    });
    return res.data;
  } catch (e) {
    console.error(e);
    throw e;
  }
};
const getFirstTwoBytes = async (chunker) => new TextDecoder().decode(await chunker(0, 2));

const makeChunkable = async (source) => {
  // dump stream to buffer
  // we don't support streams anyways (see zipreader.js)
  let initialChunker;
  let buf = null;
  if (source.type === 'stream') {
    buf = await streamToBuffer(source.location);
    initialChunker = fromBuffer(buf);
  } else if (source.type === 'buffer') {
    buf = source.location;
    initialChunker = fromBuffer(buf);
  } else {
    initialChunker = await fromDataSource(source);
  }

  const magic = await getFirstTwoBytes(initialChunker);
  // Pull first two bytes from source.
  if (magic === 'PK') {
    return initialChunker;
  }
  // Unwrap if it's html.
  // If NOT zip (html), convert/dump to buffer, unwrap, and continue.
  const htmlBuf = buf || (await initialChunker());
  const zipBuf = TDF.unwrapHtml(htmlBuf);
  return fromBuffer(zipBuf);
};

/**
 * An abstraction for protecting and accessing data using TDF3 services.
 */
class Client {
  /**
   * Configure a TDF3 client to connect to the requested EAS.
   * @param {Object} config - configuration parameters
   * @param {AuthProvider|function} [config.authProvider] - auth request interceptor
   * @param {string} [config.easEndpoint] - root path for Entity Attribute Service (deprecated)
   * @param {string} [config.entityObjectEndpoint] - Entity Object path on an Entity Attribute Service
   * @param {string} [config.kasEndpoint] - root path for Key Access Service
   * @param {string} [config.keyRewrapEndpoint] - full path on the KAS to the rewrap endpoint
   * @param {string} [config.keyUpsertEndpoint] - full path on the KAS to the key+policy upsert endpoint
   * @param {object} [config.keypair] - explicit keypair to use to communicate with KAS
   * @param {object} [config.readerUrl] - associated TDF reader service
   * @param {object} [config.userId] - a user id to send to EAS, useful in debug mode
   * @param {function} [config.validateEntity] - validate entity by backend
   */
  constructor(config = {}) {
    const clientConfig = { ...defaultClientConfig, ...config };
    if (!clientConfig.authProvider) {
      clientConfig.authProvider = new NoAuthProvider();
    }
    const { authProvider, easEndpoint } = clientConfig;

    if (!clientConfig.kasEndpoint) {
      if (!clientConfig.keyRewrapEndpoint) {
        console.error('KAS definition not found');
      } else {
        clientConfig.kasEndpoint = clientConfig.keyRewrapEndpoint.replace(/\/rewrap$/, '');
      }
    } else {
      if (!clientConfig.keyRewrapEndpoint) {
        clientConfig.keyRewrapEndpoint = `${clientConfig.kasEndpoint}/rewrap`;
      }
      if (!clientConfig.keyUpsertEndpoint) {
        clientConfig.keyUpsertEndpoint = `${clientConfig.kasEndpoint}/upsert`;
      }
    }

    this.eas = new EAS({
      authProvider,
      // NOTE(PLAT-619) Update default entity object path to /v1/entity_object
      endpoint: clientConfig.entityObjectEndpoint || `${easEndpoint}/api/entityobject`,
    });
    this.clientConfig = clientConfig;
  }

  /**
   * Encrypt plaintext into TDF ciphertext. One of the core operations of the Virtru SDK.
   *
   * @param {object} scope - dissem and attributes for constructing the policy
   * @param {object} source - nodeJS source object of unencrypted data
   * @param {boolean} [asHtml] - If we should wrap the TDF data in a self-opening HTML wrapper
   * @param {object} [eo] - Cached EO, if available.
   * @param {object} [keypair] - explicit keypair to use to communicate with KAS. Can also be specified in constructor. If not found, generated.
   * @param {object} [metadata] - additional non-secret data to store with the TDF
   * @param {string} [mimeType] - mime type of source
   * @param {boolean} [offline] - Where to store the policy
   * @param {object} [output] - output stream. Created and returned if not passed in
   * @param {object} [rcaSource] - RCA source information
   * @param {function} [validateEntity] - Called on the EO after fetch; return `false` to fail the encrypt, e.g. if the entity has insufficient authN
   * @param {number} [windowSize] - segment size in bytes
   * @return {TDFCiphertextStream} - a {@link https://nodejs.org/api/stream.html#stream_class_stream_readable|Readable} stream containing the TDF ciphertext.
   * @see EncryptParamsBuilder
   */
  async encrypt({
    scope,
    source,
    asHtml = false,
    eo = null,
    keypair = null,
    metadata = {},
    mimeType = null,
    offline = false,
    output = null,
    rcaSource = null,
    validateEntity = null,
    windowSize = DEFAULT_SEGMENT_SIZE,
  }) {
    if (rcaSource && asHtml) throw new Error('rca links should be used only with zip format');
    const { entityObject, ephemeralKeyPair } = await this.auth({ keypair, eo });
    if (validateEntity && !validateEntity(entityObject)) {
      throw new Error('Entity failed validation');
    }

    const policyObject = await this._createPolicyObject(scope);
    // TODO: Refactor underlying builder to remove some of this unnecessary config.
    const tdf = TDF.create()
      .setPrivateKey(ephemeralKeyPair.privateKey)
      .setPublicKey(ephemeralKeyPair.publicKey)
      .setEncryption({
        type: 'split',
        cipher: 'aes-256-gcm',
      })
      .setDefaultSegmentSize(windowSize)
      // set root sig and segment types
      .setIntegrityAlgorithm('hs256', 'gmac')
      .addContentStream(source, mimeType)
      .setPolicy(policyObject)
      .setEntity(entityObject)
      .setAuthProvider(this.clientConfig.authProvider);

    if (this.clientConfig.kasPublicKey && this.clientConfig.kasEndpoint) {
      tdf.addKeyAccess({
        type: offline ? 'wrapped' : 'remote',
        metadata,
        publicKey: this.clientConfig.kasPublicKey,
        url: this.clientConfig.kasEndpoint,
      });
    } else {
      // This will use the EO's default attribute's KAS information.
      tdf.addKeyAccess({
        type: offline ? 'wrapped' : 'remote',
        metadata,
      });
    }

    const stream = (!asHtml && output) || new TDFCiphertextStream(windowSize);
    const byteLimit = asHtml ? HTML_BYTE_LIMIT : GLOBAL_BYTE_LIMIT;
    const { upsertResponse, tdfSize } = await tdf.writeStream(stream, byteLimit, rcaSource);
    if (rcaSource) {
      const url = upsertResponse[0][0].storageLinks.payload.upload;
      await uploadBinaryToS3(stream, url, tdfSize);
    }
    if (!asHtml) {
      return stream;
    }

    // Wrap if it's html.
    // FIXME: Support streaming for html format.
    const htmlBuf = TDF.wrapHtml(
      await stream.toBuffer(),
      JSON.stringify(tdf.manifest),
      this.clientConfig.readerUrl
    );
    const htmlStream = output || new TDFCiphertextStream(windowSize);
    htmlStream.push(htmlBuf);
    htmlStream.push(null);
    return htmlStream;
  }

  /**
   *
   * @param {object} [eo] - Cached EO, if available.
   * @param {object} [keypair] - Additional additional keydata associated with EO
   * @returns authentication token and key for private communication with it
   */
  async auth({ keypair, eo }) {
    if (eo && (!keypair || keypair.publicKey !== eo.publicKey)) {
      throw Error(
        `Mismatched ephemeral key and EO key cert ${JSON.stringify(keypair)} ${JSON.stringify(eo)}`
      );
    }
    const ephemeralKeyPair = keypair || (await this._getOrCreateKeypair(keypair));
    const entityObject = eo || (await this._fetchEntityObject(ephemeralKeyPair));
    return { ephemeralKeyPair, entityObject };
  }

  /**
   * Decrypt TDF ciphertext into plaintext. One of the core operations of the Virtru SDK.
   *
   * @param {object} - Required. All parameters for the decrypt operation, generated using {@link DecryptParamsBuilder#build|DecryptParamsBuilder's build()}.
   * @param {object} source - A data stream object, one of remote, stream, buffer, etc. types.
   * @param {object} [eo] - Cached EO, if available.
   * @param {object} [keypair] - Additional additional keydata.
   * @param {object} [output] - A node Writeable; if not found will create and return one.
   * @param {object} [rcaSource] - RCA source information
   * @return {PlaintextStream} - a {@link https://nodejs.org/api/stream.html#stream_class_stream_readable|Readable} stream containing the decrypted plaintext.
   * @see DecryptParamsBuilder
   */
  async decrypt({
    source,
    eo = null,
    keypair = null,
    output = null,
    rcaSource = null,
    contentLength = null,
  }) {
    const { entityObject, ephemeralKeyPair } = await this.auth({ keypair, eo });
    const tdf = TDF.create()
      .setPrivateKey(ephemeralKeyPair.privateKey)
      .setPublicKey(ephemeralKeyPair.publicKey)
      .setEntity(entityObject)
      .setAuthProvider(this.clientConfig.authProvider);
    const chunker = await makeChunkable(source);
    const out = output || new PlaintextStream();

    if (contentLength) {
      out.contentLength = contentLength;
    }

    // Await in order to catch any errors from this call.
    // TODO: Write error event to stream and don't await.
    await tdf.readStream(chunker, out, rcaSource);

    return out;
  }

  /**
   * Get the unique policyId associated with TDF ciphertext. Useful for managing authorization policies of encrypted data.
   * <br/><br/>
   * The policyId is embedded in the ciphertext so this is a local operation.
   *
   * @param {object} source - Required. TDF data stream,
   * generated using {@link DecryptParamsBuilder#build|DecryptParamsBuilder's build()}.
   * @return {string} - the unique policyId, which can be used for tracking purposes or policy management operations.
   * @see DecryptParamsBuilder
   */
  async getPolicyId({ source }) {
    const chunker = await makeChunkable(source);
    const zipHelper = new ZipReader(chunker);
    const centralDirectory = await zipHelper.getCentralDirectory();
    const manifest = await zipHelper.getManifest(centralDirectory, '0.manifest.json');
    const policyJson = base64.decode(manifest.encryptionInformation.policy);
    return JSON.parse(policyJson).uuid;
  }

  /*
   * Create a policy object for an encrypt operation.
   */
  async _createPolicyObject(scope) {
    if (scope.policyObject) {
      // use the client override if provided
      return scope.policyObject;
    }
    const policyId = scope.policyId || v4();
    return {
      uuid: policyId,
      body: {
        dataAttributes: scope.attributes,
        dissem: scope.dissem,
      },
    };
  }

  /*
   * Fetch an entity object for an encrypt or decrypt operation.
   */
  async _fetchEntityObject({ publicKey }) {
    const { userId } = this.clientConfig;
    return this.eas.fetchEntityObject({
      publicKey,
      ...(userId && { userId }),
    });
  }

  /*
   * Extract a keypair provided as part of the options dict.
   * Default to using the clientwide keypair, generating one if necessary.
   */
  async _getOrCreateKeypair() {
    if (this.clientConfig.keypair) {
      return this.clientConfig.keypair;
    }
    this.clientConfig.keypair = await TDF.generateKeyPair();
    return this.clientConfig.keypair;
  }
}

export default {
  AuthProvider,
  Client,
  DecryptParamsBuilder,
  EncryptParamsBuilder,
  HttpRequest,
};
