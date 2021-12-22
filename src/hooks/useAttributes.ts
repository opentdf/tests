import { useCallback, useEffect, useState } from 'react';
import { entityClient } from "../service";
import {AttributeDefinition, AuthorityDefinition} from "../types/attributes";
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

export const useAttributesDefinitions = (authorityDefinition: AuthorityDefinition) => {
  const [attrs, setAttrs] = useState<AttributeDefinition[]>([]);
  const [getAttrs, { data, loading }] = useLazyFetch<AttributeDefinition[]>(entityClient);
  const buildConfig = useCallback((namespace) => ({ method: Method.GET, path: serverData.attributes + '/attributes' }), [authorityDefinition]);

  useEffect(() => {
    if (data) {
      setAttrs(data);
    }
  }, [data]);

  useEffect(() => {
    if (!authorityDefinition) {
      return;
    }

    getAttrs(buildConfig(authorityDefinition));
  }, [authorityDefinition,buildConfig,getAttrs]);

  return { attrs, getAttrs: (namespace: string) => getAttrs(buildConfig(namespace)), loading };
};
