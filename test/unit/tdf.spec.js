import { expect } from 'chai';
import * as crypto from 'crypto';

import { KeyAccessError } from '../../src/errors';
import { AttributeSet } from '../../src/models';
import { TDF } from '../../src';
import getMocks from '../../mocks';

const Mocks = getMocks();

async function sleep(msec) {
  return new Promise((resolve) => setTimeout(resolve, msec));
}

describe('TDF', () => {
  it('constructs', () => {
    const actual = new TDF();
    expect(actual).to.be.an.instanceof(TDF);
  });

  it('creates', () => {
    const actual = TDF.create();
    expect(actual).to.be.an.instanceof(TDF);
  });

  it('sets the entity object', async () => {
    const testCase = new TDF();
    const expected = await Mocks.getEntityObject();
    testCase.setEntity(expected);
    expect(testCase.entity).to.deep.equal(expected);
  });

  it("harvests the entity object's attributes when entity is set", async () => {
    const testCase = new TDF();
    const expected = await Mocks.getEntityObject([
      {
        attribute:
          'https://aa.virtru.com/attr/unique-identifier/value/7b738968-131a-4de9-b4a1-c922f60583e3',
        displayName: '7b738968-131a-4de9-b4a1-c922f60583e3',
      },
      {
        attribute:
          'https://aa.virtru.com/attr/primary-organization/value/7b738968-131a-4de9-b4a1-c922f60583e3',
        displayName: '7b738968-131a-4de9-b4a1-c922f60583e3',
      },
    ]);
    const aSet = new AttributeSet();
    await aSet.addJwtAttributes(expected.attributes);
    const expectedUrls = aSet.getUrls();
    testCase.setEntity(expected);
    // setEntity launches an async decryption process in the AttributeSet,
    // but it returns immediately.  Wait a few ms for that process to
    // complete before running the assertions.
    await sleep(25);
    // verify that the attributes were extracted
    const actual = testCase.attributeSet;
    expect(actual.attributes.map(({ attribute }) => attribute)).to.have.deep.members(expectedUrls);
  });

  it('sets the default attribute if one is present in the entity object', async () => {
    const testCase = new TDF();
    const expected = await Mocks.getEntityObject([{ isDefault: true }]);
    const aSet = new AttributeSet();
    await aSet.addJwtAttributes(expected.attributes);
    const expectedDefault = aSet.getDefault();
    testCase.setEntity(expected);
    // setEntity launches an async decryption process in the AttributeSet,
    // but it returns immediately.  Wait a few ms for that process to
    // complete before running the assertions.
    await sleep(25);
    const actual = testCase.attributeSet.getDefault();
    expect(expectedDefault.attribute).to.deep.equal(actual.attribute);
  });

  it('does not set a default attribute if one is not present in the entity object', async () => {
    const testCase = new TDF();
    const expected = await Mocks.getEntityObject([]);
    testCase.setEntity(expected);
    // setEntity launches an async decryption process in the AttributeSet,
    // but it returns immediately.  Wait a few ms for that process to
    // complete before running the assertions.
    await sleep(25);
    const actual = testCase.attributeSet.getDefault();
    expect(actual).to.be.null;
  });

  it('resets the default attribute when a new EO is loaded with a different default attr', async () => {
    // NOTE - this test is here more to document what the TDF class will do, not as a
    // lock-down of the "right" behavior. If and when we start loading EOs from multiple
    // EAS's we will have exceeded the current very simple one-EO, one-default assumption.
    const url_first = 'https://api.virtru.com/attr/default/value/default_first';
    const url_second = 'https://api.virtru.com/attr/default/value/default_second';
    const testCase = new TDF();
    const first = await Mocks.getEntityObject([
      {
        attribute: url_first,
        isDefault: true,
      },
    ]);
    const second = await Mocks.getEntityObject([
      {
        attribute: url_second,
        isDefault: true,
      },
    ]);
    testCase.setEntity(first);
    await sleep(25);
    testCase.setEntity(second);
    await sleep(25);
    // The second default attribute should be loaded.
    expect(testCase.attributeSet.getDefault().attribute).to.deep.equal(url_second);
    // The first attribute should be gone. Only one default per set.
    expect(testCase.attributeSet.attributes[0].attribute).to.deep.equal(url_second);
    expect(testCase.attributeSet.attributes).to.have.lengthOf(1);
  });

  it('fails to wrap when no pubkey/kasurl data is available.', async () => {
    const testCase = new TDF();
    const entityObject = await Mocks.getEntityObject(); // Empty; no default attribute
    testCase.setEntity(entityObject);
    expect(() => testCase.addKeyAccess({ type: 'wrapped' })).to.throw(KeyAccessError);
    expect(() => testCase.addKeyAccess({ type: 'remote' })).to.throw(KeyAccessError);
  });

  it('uses the default attribute pubkey by default when set', async () => {
    const testCase = new TDF();
    testCase.setEncryption({
      type: 'split',
      cipher: 'aes-256-gcm',
    });
    const pubKey = 'this distinctive string is the default pubKey';
    const kasUrl = 'this distinctive string is the default kasUrl';
    const defaultEO = await Mocks.getEntityObject([{ isDefault: true, pubKey, kasUrl }]);
    // TODO - make all the setters return promises that resolve to <TDF instance> to
    // eliminate these fragile "sleep" hacks.
    testCase.setEntity(defaultEO);
    await sleep(20); // give a little time for the EO attribute JWTs to decrypt.
    testCase.addKeyAccess({ type: 'wrapped' });
    await sleep(20); // give a little time for the key wrap to complete.
    const keyAccess = testCase.encryptionInformation.keyAccess[0];
    expect(keyAccess.url).to.deep.equal(kasUrl);
    expect(keyAccess.publicKey).to.deep.equal(pubKey);
    expect(testCase.encryptionInformation.keyAccess).to.have.lengthOf(1);
  });

  it('uses the method-provided pubkey and kasUrl when set explicitly', async () => {
    const testCase = new TDF();
    testCase.setEncryption({
      type: 'split',
      cipher: 'aes-256-gcm',
    });
    const pubKey = 'this distinctive string is the default pubKey';
    const kasUrl = 'this distinctive string is the default kasUrl';
    const defaultEO = await Mocks.getEntityObject([{ isDefault: true }]);
    // TODO - make all the setters return promises that resolve to <TDF instance> to
    // eliminate these fragile "sleep" hacks.
    testCase.setEntity(defaultEO);
    await sleep(20); // give a little time for the EO attribute JWTs to decrypt.
    testCase.addKeyAccess({ type: 'wrapped', url: kasUrl, publicKey: pubKey });
    await sleep(20); // give a little time for the key wrap to complete.
    const keyAccess = testCase.encryptionInformation.keyAccess[0];
    expect(keyAccess.url).to.deep.equal(kasUrl);
    expect(keyAccess.publicKey).to.deep.equal(pubKey);
    expect(testCase.encryptionInformation.keyAccess).to.have.lengthOf(1);
  });

  it('uses the a specific attribute when attributeUrl is set', async () => {
    const testCase = new TDF();
    testCase.setEncryption({
      type: 'split',
      cipher: 'aes-256-gcm',
    });
    const pubKey = 'this distinctive string is the default pubKey';
    const kasUrl = 'this distinctive string is the default kasUrl';
    const attributeUrl = 'http://acme.com/attr/projects/value/anvil';
    const entity = await Mocks.getEntityObject([
      { isDefault: true },
      { attribute: attributeUrl, pubKey, kasUrl },
    ]);
    // TODO - make all the setters return promises that resolve to <TDF instance> to
    // eliminate these fragile "sleep" hacks.
    testCase.setEntity(entity);
    await sleep(20); // give a little time for the EO attribute JWTs to decrypt.
    testCase.addKeyAccess({
      type: 'wrapped',
      url: 'this is NOT the kas url that should be used',
      publicKey: 'this is NOT the public key that should be used',
      attributeUrl,
    });
    await sleep(20); // give a little time for the key wrap to complete.
    const keyAccess = testCase.encryptionInformation.keyAccess[0];
    expect(keyAccess.url).to.deep.equal(kasUrl);
    expect(keyAccess.publicKey).to.deep.equal(pubKey);
    expect(testCase.encryptionInformation.keyAccess).to.have.lengthOf(1);
  });

  it('Encodes the postMessage origin properly in wrapHtml', () => {
    const cipherText = 'abcezas123';
    const transferUrl = 'https://local.virtru.com/start?htmlProtocol=1';
    const wrapped = TDF.wrapHtml(cipherText, JSON.stringify({ thisIs: 'metadata' }), transferUrl);
    const rawHtml = wrapped.toString();
    expect(rawHtml).to.include("'https://local.virtru.com', [channel.port2]);");
  });

  it('Round Trip wrapHtml and unwrapHtml', () => {
    const cipherText = crypto.randomBytes(12);
    const transferUrl = 'https://local.virtru.com/start?htmlProtocol=1';
    const wrapped = TDF.wrapHtml(cipherText, JSON.stringify({ thisIs: 'metadata' }), transferUrl);
    const unwrapped = TDF.unwrapHtml(wrapped);
    expect(unwrapped).to.deep.equal(new Uint8Array(cipherText));
  });
});
