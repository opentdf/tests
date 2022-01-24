import { assert } from 'chai';

import { EAS } from '../../../src/client/auth';

describe('EAS', function () {
  it('auth provider allows updates to headers', async () => {
    const publicKey = 'exampleKey';
    let authed = false;
    let requested = false;
    const eas = new EAS({
      authProvider: (r) => {
        r.params.exampleParam = 'exampleValue';
        assert.equal(r.params.publicKey, 'exampleKey');
        authed = true;
      },
      endpoint: 'endpoint',
      requestFunctor: (params) => {
        assert.isTrue(authed);
        assert.equal(params.url, 'endpoint');
        assert.isOk(params.data);
        assert.equal(params.data.publicKey, 'exampleKey');
        assert.equal(params.data.exampleParam, 'exampleValue');
        requested = true;
        return params;
      },
    });
    // Return the promise so mochajs can resolve it.
    const response = await eas.fetchEntityObject({ publicKey });
    assert.equal(response.exampleParam, 'exampleValue');
    assert.isTrue(requested);
  });

  it('extra params are passed to endpoint', async () => {
    const publicKey = 'exampleKey';
    const a = 'a';
    const b = 'b';
    let requested = false;
    const eas = new EAS({
      authProvider: () => {
        // Ignore
      },
      endpoint: 'endpoint',
      requestFunctor: (params) => {
        assert.equal(params.data.publicKey, 'exampleKey');
        assert.equal(params.data.a, 'a');
        assert.equal(params.data.b, 'b');
        requested = true;
        return params;
      },
    });
    // Return the promise so mochajs can resolve it.
    const response = await eas.fetchEntityObject({ publicKey, a, b });
    assert.equal(response.a, 'a');
    assert.equal(response.b, 'b');
    assert.isTrue(requested);
  });
});
