import { useCallback, useEffect, useState } from 'react';
import { attributesClient } from "../service";
import { Attribute } from "../types/attributes";
import { Method } from "../types/enums";
import { useLazyFetch } from './useFetch';


export const useDefinitionAttributes = (authority: string) => {
  const [attrs, setAttrs] = useState<Attribute[]>([]);
  const [getAttrs, { data, loading }] = useLazyFetch<Attribute[]>(attributesClient);

  const buildConfig = useCallback((authority) => ({
    method: Method.GET,
    path: authority ? `/definitions/attributes?authority=${authority}` : '/definitions/attributes'
  }), []);

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

type DefAttrsQueryParams = {
  name: string;
  order: string;
  limit: number;
  offset: number;
  sort: string;
}

export const useAttributesFilters = (authority: string, query: DefAttrsQueryParams) => {
  const [getAttrs, { data, loading, headers }] = useLazyFetch<Attribute[]>(attributesClient);
  const xTotalCount: number = Number(headers?.['x-total-count'] ?? 0);

  useEffect(() => {
    if (authority) {
      const config = { method: Method.GET, path: `/definitions/attributes`, params: {} };

      // Remove empty query params
      const queryParams = Object.fromEntries(Object.entries(query).filter(([_, v]) => v));

      config.params = { authority, ...queryParams }
      getAttrs(config);
    }
  }, [authority, query, getAttrs]);

  return { attrs: data || [], loading, xTotalCount };
};
