/* globals page */
/* eslint-disable import/no-extraneous-dependencies */
const { resolve } = require('path');
const interceptRequestEnablePKI = require('../helpers/interceptRequestEnablePKI');
const tests = require('../helpers/buildOpenApiTests');

jest.setTimeout(3 * 60 * 1000);

expect.extend({
  // Add expectation for a value existing in an array
  toBeIncludedIn(received, array) {
    const pass = array.includes(received);
    if (pass) {
      return {
        message: () => `expected ${received} not to be in [${array}]`,
        pass: true,
      };
    }
    return {
      message: () => `expected ${received} to be in [${array}]`,
      pass: false,
    };
  },
});

describe('Request Client Tests', () => {
  const results = { kas: [], eas: [] };
  const unexpectedErrors = [];

  // Setup page
  beforeAll(async () => {
    await page.goto(`file://${resolve(`${__dirname}/requestClientTest.html`)}`);

    // await interceptRequestEnablePKI(page);

    // On each console log the test results
    page.on('console', ({ _text }) => {
      try {
        // Parse the text to organize results by service
        const { service, ...rest } = JSON.parse(_text);
        if (!results[service]) results[service] = [];
        results[service].push({ ...rest, _text });
      } catch (e) {
        // Ignore since we're catching it with Axios
        if (_text.match(/^Failed to load resource:/)) return;
        // Add unexpected console errors
        unexpectedErrors.push(_text);
      }
    });

    // Wait for tests to complete
    await page.waitForSelector('.done', { waitUntil: 'load', timeout: 0 });
  });

  /**
   * Test each endpoint
   *
   * Iterate over test results. This is required since Jest doesn't allow for procedural tests
   * `test.each` will build the test scaffolding before setups `beforeAll` or `beforeEach`.
   *
   * @param {*} testData
   */
  const testEndpoint = (testData) => (
    expectedMethod,
    expectedUrl,
    expectedPathRegexp,
    expectedStatuses
  ) => {
    // Find the correct test data
    const testResult = testData.find(({ method, url }) => {
      return expectedPathRegexp.test(url) && expectedMethod.toUpperCase() === method.toUpperCase();
    });

    // Expect path and method to be called
    expect(testResult).not.toEqual(undefined);

    // This test is to help debug failures
    if (testResult.status >= 400) {
      expect({
        detail: testResult.data.detail,
        status: testResult.status,
      }).toEqual({
        detail: false, // used to capture proxy errors
        status: expectedStatuses.includes(testResult.status) ? testResult.status : expectedStatuses,
      });
    }

    // Expect status to be one of the defined statuses
    expect(testResult.status).toBeIncludedIn(expectedStatuses);

    // TODO Validate data with response schema. Requires resolving OpenAPI $refs
  };

  /**
   * Standup endpoint test
   *
   * Build tests from expected test results. This is required since Jest doesn't allow for procedural tests
   * `test.each` will build the test scaffolding before setups `beforeAll` or `beforeEach`.
   *
   * @param {array} expected expected data
   * @param {array} actual actual data
   */
  const standupEndpointTest = (expected, actual) => {
    test.each(expected)('%s %s', testEndpoint(actual));
  };

  describe('EAS endpoints', () => standupEndpointTest(tests.eas, results.eas));

  describe('KAS endpoints', () => standupEndpointTest(tests.kas, results.kas));

  test('no unexpected console errors', () => {
    expect(unexpectedErrors).toEqual([]);
  });
});
