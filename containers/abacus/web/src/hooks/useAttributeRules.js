import { useState, useEffect } from 'react';
import generateClient, { SERVICE_ATTRIBUTES } from '@/helpers/requestClient';

const client = generateClient(SERVICE_ATTRIBUTES);

function useAttributeRules(selectedAuthorityNamespace) {
  const [attributeRules, setAttributeRules] = useState([]);

  useEffect(() => {
    async function fetchData() {
      if (selectedAuthorityNamespace) {
        const { data } = await client.read_attribute_v1_attrName_post({
          namespace: selectedAuthorityNamespace,
        });
        setAttributeRules(data);
      } else {
        // TODO fix next tick hack for react-hooks tests
        await new Promise((resolve) => resolve());
        setAttributeRules([]);
      }
    }

    fetchData();
  }, [selectedAuthorityNamespace]);

  return attributeRules;
}

export default useAttributeRules;
