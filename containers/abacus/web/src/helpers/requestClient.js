import OpenApiAxios from 'openapi-client-axios';
// eslint-disable-next-line import/no-unresolved
import claimsOpenApi from '@claims/openapi.json';
// eslint-disable-next-line import/no-unresolved
import attributesOpenApi from '@attributes/openapi.json';
// eslint-disable-next-line import/no-unresolved
import entitlementOpenApi from '@entitlement/openapi.json';

export const SERVICE_EAS = 'eas';
export const SERVICE_CLAIMS = 'claims';
export const SERVICE_ATTRIBUTES = 'attributes';
export const SERVICE_ENTITLEMENT = 'entitlement';
export const BEHIND_EAS = 'behindEas';

export const generateKeycloakAuthHeaders = () => {
  const headers = {};

  if (typeof window !== 'undefined') {
    const token = window.sessionStorage.getItem('keycloak-token');
    headers.authorization = `Bearer ${token}`;
    headers.accept = 'application/json';
  }

  return headers;
};

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '';
export const OIDC_BASE_URL = process.env.OIDC_BASE_URL || `${API_BASE_URL}/keycloak/auth/`;

export default function generateClient(service, customUrl, initSync = true) {
  let definition;
  let description;
  switch (service) {
    case SERVICE_CLAIMS:
      definition = claimsOpenApi;
      description = 'claims';
      break;
    case SERVICE_ATTRIBUTES:
      definition = attributesOpenApi;
      description = 'attributes';
      break;
    case SERVICE_EAS:
      definition = entitlementOpenApi;
      description = 'eas';
      break;
    case SERVICE_ENTITLEMENT:
      definition = entitlementOpenApi;
      description = 'entitlement';
      break;
    case BEHIND_EAS:
      definition = entitlementOpenApi;
      description = 'behind EAS Server';
      break;
    default:
      throw new Error(`Service, ${service}, not found.`);
  }

  let url;
  const serviceEndpoint = `/${service}`;
  let serviceUrl;
  if (service === SERVICE_CLAIMS) {
    serviceUrl = process.env.NEXT_PUBLIC_EAS_API_URL;
  }
  if (service === BEHIND_EAS) {
    serviceUrl = 'http://localhost:65432/';
  }
  if (serviceUrl) {
    url = serviceUrl;
  } else {
    url = API_BASE_URL + serviceEndpoint;
  }

  const client = new OpenApiAxios({
    definition,
    withServer: { url, description },
  });

  return initSync ? client.initSync() : client;
}
