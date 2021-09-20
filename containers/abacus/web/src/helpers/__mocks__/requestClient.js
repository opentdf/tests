import { apiMethodResponses } from '@/__fixtures__/requestData';

jest.createMockFromModule('../requestClient');

const mockClient = jest.fn();

/**
 * Mock override default resolve value
 *
 * Since we are resolving the default fixture data we want to make sure we can override this at will
 *
 * @returns mockClient
 */
mockClient.mockOverrideDefaultResolveValue = () => {
  mockClient.mock.override = true;
  return mockClient;
};

// Extract the original functions
const { mockClear, mockReset } = mockClient;

// Override the mockClear to clear the override
mockClient.mockClear = () => {
  mockClear();
  mockClient.mock.override = false;
};

// Override the mockReset to clear the override
mockClient.mockReset = () => {
  mockReset();
  mockClient.mock.override = false;
};

/**
 * Get the fixture data from the request data fixture
 *
 * @param {string} method name of the method which is being called
 * @param {array} args array of arguments passed to the method
 * @returns {*|undefined} returns the fixture data or undefined
 */
function getFixtureData(method, args) {
  // If the fixture returns a function, then call it and return the response
  if (typeof apiMethodResponses[method] === 'function') {
    return apiMethodResponses[method](...args);
  }
  // Return the fixture data
  return apiMethodResponses[method];
}

function generateClient() {
  // Proxy the methods to support current and future methods dynamically
  return new Proxy(
    {},
    {
      get: (target, name) => (...args) => {
        // If not overriding the default mock data
        if (mockClient.mock.override !== true) {
          // Resolve the mock with the fixture data
          mockClient.mockResolvedValueOnce({ data: getFixtureData(name, args) });
        }
        // Call the mock function
        return mockClient(name, args);
      },
    }
  );
}

// Add the mockClient to the generate function
generateClient.mockClient = mockClient;

export default generateClient;
