import { useCallback, useEffect, useState } from 'react';
import { entityClient } from "../service";
import { AttributeDefinition } from "../types/attributes";
import { Entitlements } from "../types/entitlements";
import { Method } from "../types/enums";
import { useLazyFetch } from './useFetch';

// @ts-ignore
const serverData = window.SERVER_DATA;

export const useAttributes = () => {
  const [attributes, setAttributes] = useState<Entitlements[]>([]);
  const [getAttrs, { data }] = useLazyFetch<Entitlements[]>(entityClient);

  const buildConfig = useCallback((entityId) => ({ method: Method.GET, path: serverData.attributes + `/attributes` }), []);

  useEffect(() => {
    if (data) {
      setAttributes(data);
    }
  }, [data]);

  return { attributes, getAttrs: (entityId: string) => getAttrs(buildConfig(entityId)) };
};

export const useAttrs = (namespace: string) => {
  const [attrs, setAttrs] = useState<AttributeDefinition[]>([]);
  const [getAttrs, { data, loading }] = useLazyFetch<AttributeDefinition[]>(entityClient);

  const buildConfig = useCallback((namespace) => ({ method: Method.POST, path: serverData.attributes + `/attributes`, data: { namespace } }), []);

  useEffect(() => {
    if (data) {
      setAttrs(data);
    }
  }, [data]);

  useEffect(() => {
    if (!namespace) {
      return;
    }

    getAttrs(buildConfig(namespace));
  }, [namespace]);

  return { attrs, getAttrs: (namespace: string) => getAttrs(buildConfig(namespace)), loading };
};
