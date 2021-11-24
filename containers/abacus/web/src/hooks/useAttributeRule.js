import { useState, useEffect } from 'react';
import generateClient, { SERVICE_ATTRIBUTES } from '@/helpers/requestClient';

const client = generateClient(SERVICE_ATTRIBUTES);

function useAttributeRule(name, value, namespace) {
  const [attributeRule, setAttributeRule] = useState([]);

  useEffect(() => {
    async function fetchData() {
      if (name !== undefined && value !== undefined && namespace !== undefined) {
        const { data } = await client.read_attribute_v1_attr_get({ name, value, namespace });
        setAttributeRule(data);
      }
    }

    fetchData();
  }, [name, value, namespace]);

  return attributeRule;
}

export default useAttributeRule;
