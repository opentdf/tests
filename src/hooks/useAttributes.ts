import { useCallback, useEffect, useState } from 'react';
import { entityClient } from "../service";
import { Attribute } from "../types/attributes";
import { EntityAttribute } from "../types/entitlements";
import { Method } from "../types/enums";
import { useLazyFetch } from './useFetch';

export const useAttributes = () => {
  const [attributes, setAttributes] = useState<EntityAttribute[]>([]);
  const [getAttrs, { data }] = useLazyFetch<EntityAttribute[]>(entityClient);

  const buildConfig = useCallback((entityId) => ({ method: Method.GET, path: `/attributes/v1/attrName/${entityId}/attribute` }), []);

  useEffect(() => {
    if (data) {
      setAttributes(data);
    }
  }, [data]);

  return { attributes, getAttrs: (entityId: string) => getAttrs(buildConfig(entityId)) };
};

export const useAttrs = (namespace: string) => {
  const [attrs, setAttrs] = useState<Attribute[]>([]);
  const [getAttrs, { data }] = useLazyFetch<Attribute[]>(entityClient);

  const buildConfig = useCallback((namespace) => ({ method: Method.POST, path: `/attributes/v1/attrName`, data: { namespace } }), []);

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

  return { attrs, getAttrs: (namespace: string) => getAttrs(buildConfig(namespace)) };
};
