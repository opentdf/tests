import { useState, useEffect } from 'react';
import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';

const client = generateClient(SERVICE_EAS);

function useAuthorityNamespaces({ isDefault = null } = {}) {
  const [authorityNamespaces, setAuthorityNamespaces] = useState([]);
  const params = {};

  useEffect(() => {
    async function fetchData() {
      try {
        if (isDefault) {
          params.isDefault = true;
        }
        const result = await client['src.web.authority_namespace.get'](params);
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
