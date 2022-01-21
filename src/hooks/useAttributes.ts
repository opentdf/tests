import { useCallback, useEffect, useState } from 'react';
import { attributesClient } from "../service";
import { Attribute } from "../types/attributes";
import { Method } from "../types/enums";
import { useLazyFetch } from './useFetch';


export const useDefinitionAttributes = (authority: string) => {
  const [attrs, setAttrs] = useState<Attribute[]>([]);
  const [getAttrs, { data, loading }] = useLazyFetch<Attribute[]>(attributesClient);

  //TODO: Does this work with authority param?
  const buildConfig = useCallback((authority) => ({ method: Method.GET, path: `/attributes/definitions/attributes` }), []);

  useEffect(() => {
    if (data) {
      setAttrs(data);
    }
  }, [data]);

  useEffect(() => {
    getAttrs(buildConfig(authority));
  }, [authority, buildConfig, getAttrs]);

  return { attrs, getAttrs: (authority: string) => getAttrs(buildConfig(authority)), loading };
};
