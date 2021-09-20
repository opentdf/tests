const { openApi } = require('./getRootConfig');

const tests = {
  eas: [],
};

// Replace the `{word}` schema with regex ([^\]+)
function getExp(urlPath) {
  return urlPath.replace(/\{[^}]+\}/g, '[^\\/]+');
}

// Generate tests from OpenAPI schema
Object.keys(openApi).forEach((serviceName) => {
  const service = openApi[serviceName];
  Object.keys(service.paths).forEach((pathName) => {
    const urlPath = service.paths[pathName];
    Object.keys(urlPath).forEach((methodName) => {
      const methodObj = urlPath[methodName];
      const statusCodes = Object.keys(methodObj.responses).map((code) => parseInt(code, 10));
      // Order of these values are related to `tests.each` in requestClient.test.js
      tests[serviceName].push([methodName, pathName, new RegExp(getExp(pathName)), statusCodes]);
    });
  });
});

module.exports = tests;
