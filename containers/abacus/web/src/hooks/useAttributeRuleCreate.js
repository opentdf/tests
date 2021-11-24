/* eslint-disable dot-notation */
import { createContext, useEffect, useRef, useState } from 'react';
import generateClient, { SERVICE_ATTRIBUTES } from '@/helpers/requestClient';

export const AttributeCreateContext = createContext({});

const client = generateClient(SERVICE_ATTRIBUTES);

const useAttributeRuleCreate = () => {
  const [attributeRule, setAttributeRule] = useState({});
  const componentJustMounted = useRef(true);

  useEffect(() => {
    async function postData() {
      const { data } = client['create_attribute_v1_attr_post'](null, attributeRule);
      setAttributeRule(data);
    }
    if (!componentJustMounted.current) {
      postData();
    }
    componentJustMounted.current = false;
  }, [attributeRule]);

  return { attributeRule, setAttributeRule };
};

export default useAttributeRuleCreate;
