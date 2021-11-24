import { useState, useEffect } from 'react';
import generateClient, { SERVICE_ATTRIBUTES } from '@/helpers/requestClient';

const client = generateClient(SERVICE_ATTRIBUTES);

function useAuthorityNamespaces({ isDefault = null } = {}) {
  const [authorityNamespaces, setAuthorityNamespaces] = useState([]);
  const params = {};

  useEffect(() => {
    async function fetchData() {
      try {
        if (isDefault) {
          params.isDefault = true;
        }
        const result = await client.read_authority_namespace_v1_authorityNamespace_get(params);
        setAuthorityNamespaces(result.data);
      } catch (e) {
        console.error(e.response);
      }
    }
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isDefault]);

  return authorityNamespaces;
}

export default useAuthorityNamespaces;
