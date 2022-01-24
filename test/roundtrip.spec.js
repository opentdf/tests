import chai from 'chai';
import { Readable } from 'stream';
import sinon from 'sinon';
import getMocks from '../mocks';

import { Client, TDF } from '../src';

const { assert } = chai;

const Mocks = getMocks();

const kasPublicKey = TDF.extractPemFromKeyString(Mocks.kasPublicKey);

function tdfSandbox() {
  const sandbox = sinon.createSandbox();
  const tdf1 = TDF.create();
  sandbox.replace(
    TDF,
    'create',
    sandbox.fake(() => tdf1)
  );
  sandbox.spy(tdf1, '_generateManifest');
  sandbox.stub(tdf1, 'unwrapKey').callsFake(async (manifest) => {
    assert.nestedProperty(manifest, 'encryptionInformation.keyAccess');
    const keyInfo = tdf1._generateManifest.lastCall.args[0];
    return {
      reconstructedKeyBinary: keyInfo.unwrappedKeyBinary,
      metadata: {},
    };
  });
  return sandbox;
}

const kasUrl = `http://localhost:4000/`;

describe('Local roundtrip Tests', () => {
  it('roundtrip string', async () => {
    const sandbox = tdfSandbox();
    try {
      const eo = await Mocks.getEntityObject();
      const scope = Mocks.getScope();

      const plainString = 'Plain string';
      const plainStream = new Readable();
      plainStream.push(plainString);
      plainStream.push(null);

      const client = new Client.Client({
        kasEndpoint: kasUrl,
        kasPublicKey,
        readerUrl: 'https://local.virtru.com',
      });

      const ct = await client.encrypt({
        asHtml: true,
        keypair: { publicKey: Mocks.entityPublicKey, privateKey: Mocks.entityPrivateKey },
        eo,
        metadata: Mocks.getMetadataObject(),
        offline: true,
        scope,
        source: plainStream,
        windowSize: 1024 * 1024,
      });
      const roundTripped = await client.decrypt({
        eo,
        keypair: { publicKey: Mocks.entityPublicKey, privateKey: Mocks.entityPrivateKey },
        source: { type: 'stream', location: ct },
      });
      const txt = await roundTripped.toString();
      assert.equal(txt, plainString);
    } finally {
      sandbox.restore();
    }
  });
});
