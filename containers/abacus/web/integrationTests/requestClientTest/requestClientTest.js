/* globals window document */

import generateClient from '@/helpers/requestClient';
import easYmlFile from '@easRoot/openapi.yaml';

const SERVICE_EAS = 'eas';

const easClient = generateClient('eas', 'https://local.virtru.com/eas/');

const getOperationIds = (ymlFile) => {
  const operationIds = [];
  Object.values(ymlFile.paths)
    .map((paths) => Object.values(paths))
    .forEach((paths) => paths.forEach(({ operationId }) => operationIds.push(operationId)));
  return operationIds;
};

const getResponseStatus = ({ reason, value }) => {
  const {
    config: { url, method },
  } = reason || value;
  const { data, status } = (reason && reason.response) || value;
  return { url, method, status, data };
};

const mapMethods = (method) => method({
    name: 'name',
    value: 'value',
    userId: 'userId',
  });

const validateResponse = (service) => (response) => {
  if (typeof response !== 'object') return;

  const expected = {
    status: 200,
  };

  console.log(JSON.stringify({ service, ...response, _expected: expected }).replaceAll(',', ', '));
};

function done() {
  const div = document.createElement('div');
  div.className = 'done';
  document.body.append(div);
}

async function runTest() {
  // All request methods named as operationIds from yaml file. We get all operation ids from
  // yml file and trigger client methods. All requests should be found responded
  const easMethods = getOperationIds(easYmlFile).map((methodName) => easClient[methodName]);
  const easResponses = await Promise.allSettled(easMethods.map(mapMethods));
  easResponses.map(getResponseStatus).forEach(validateResponse(SERVICE_EAS));

  done();
}

if (window && document) {
  runTest().catch((e) => console.error('Uncaught error', e));
}
