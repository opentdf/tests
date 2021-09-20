import OpenApiAxios from 'openapi-client-axios';
import easOpenApi from '@easRoot/openapi.yaml';

export const SERVICE_EAS = 'eas';

export default function generateClient(service, customUrl, initSync = true) {
  let definition;
  let description;
  switch (service) {
    case SERVICE_EAS:
      definition = easOpenApi;
      description = 'EAS Server';
      break;
    default:
      throw new Error(`Service, ${service}, not found.`);
  }

  let url;
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || '';
  const serviceEndpoint = `/${service}`;
  let serviceUrl;
  if (service === SERVICE_EAS) {
    serviceUrl = process.env.NEXT_PUBLIC_EAS_API_URL;
  }
  if (serviceUrl) {
    url = serviceUrl;
  } else {
    url = apiBaseUrl + serviceEndpoint;
  }

  const client = new OpenApiAxios({
    definition,
    withServer: { url, description },
  });

  return initSync ? client.initSync() : client;
}
