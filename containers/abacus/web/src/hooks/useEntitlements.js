import { useState, useEffect, createContext } from 'react';
import generateClient, {
  generateKeycloakAuthHeaders,
  SERVICE_ENTITLEMENT,
} from '@/helpers/requestClient';

const client = generateClient(SERVICE_ENTITLEMENT);

/**
 * Hook that makes fetches Entitlement
 * @param params for request, that can adds body, query, rout, cookie etc.
 * Use this notation https://github.com/anttiviljami/openapi-client-axios#parameters
 * @param method
 */
function useEntitlements(params = null, method = 'GET') {
  const [entitlements, setEntitlements] = useState({});
  const [isLoading, setFetch] = useState(false);

  useEffect(() => {
    async function fetchData() {
      client.interceptors.request.use((config) => {
        // eslint-disable-next-line no-param-reassign
        config.headers = {
          ...config.headers,
          ...generateKeycloakAuthHeaders(),
        };
        return config;
      });
      const httpMethods = {
        GET: 'read_entity_attribute_relationship_v1_entity__entityId__attribute_get',
        PUT: 'create_entity_attribute_relationship_v1_entity__entityId__attribute_put',
      };
      const httpMethod = httpMethods[method];
      const requests = {
        GET: async () => client[httpMethod]({ entityId: params.entityId }),
        PUT: async () => client[httpMethod]({ entityId: params.entityId }, [params.attributeURI]),
      };
      const result = requests[method]();
      setEntitlements(result.data);
      setFetch(false);
    }

    setFetch(true);
    fetchData();
  }, [method, params]);

  return [isLoading, entitlements];
}

export default useEntitlements;
export const EntitlementsContext = createContext({});
