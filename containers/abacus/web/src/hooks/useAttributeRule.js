import { useState, useEffect } from 'react';
import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';

const client = generateClient(SERVICE_EAS);

function useAttributeRule(name, value, namespace) {
  const [attributeRule, setAttributeRule] = useState([]);

  useEffect(() => {
    async function fetchData() {
      if (name !== undefined && value !== undefined && namespace !== undefined) {
        const { data } = await client['src.web.attribute.get_value']({ name, value, namespace });
        setAttributeRule(data);
      }
    }

    fetchData();
  }, [name, value, namespace]);

  return attributeRule;
}

export default useAttributeRule;
