import { useState, useEffect } from 'react';
import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';

const client = generateClient(SERVICE_EAS);

/**
 * Hook that makes fetches Entities
 * @param params for request, that can adds body, query, rout, cookie etc.
 * Use this notation https://github.com/anttiviljami/openapi-client-axios#parameters
 */
function useEntities(params = null) {
  const [entities, setEntities] = useState([]);

  useEffect(() => {
    async function fetchData() {
      const result = await client['src.web.entity.find'](params);
      setEntities(result.data);
    }
    fetchData();
  }, [params]);

  return entities;
}

export default useEntities;
