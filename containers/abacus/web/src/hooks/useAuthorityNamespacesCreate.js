/* eslint-disable dot-notation */
import { createContext, useEffect, useRef, useState } from 'react';
import generateClient, { SERVICE_ATTRIBUTES } from '@/helpers/requestClient';

export const AuthorityNamespacesCreateContext = createContext({});

const client = generateClient(SERVICE_ATTRIBUTES);

const useAuthorityNamespacesCreate = () => {
  const [namespace, setNamespace] = useState('');
  const componentJustMounted = useRef(true);

  useEffect(() => {
    async function postData() {
      const { data } = client['create_authority_namespace_v1_authorityNamespace_post'](namespace);
      setNamespace(data);
    }
    if (!componentJustMounted.current) {
      postData();
    }
    componentJustMounted.current = false;
  }, [namespace]);

  return { namespace, setNamespace };
};

export default useAuthorityNamespacesCreate;
