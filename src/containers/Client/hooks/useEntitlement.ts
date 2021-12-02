import { AxiosResponse } from "axios";
import { useMemo } from "react";
import { Config, useLazyFetch } from "../../../hooks/useFetch";
import { entityClient } from "../../../service";
import { EntityAttribute } from '../../../types/entitlements';

export const useEntitlements = () => {
  const [makeRequest, { data, loading }] = useLazyFetch<EntityAttribute[]>(entityClient);

  const result = useMemo(() => ({ getEntitlements: makeRequest, data, loading }), [data, loading, makeRequest]);
  return result;
};

export const useUpdateEntitlement = (): [(config: Config) => Promise<AxiosResponse<any, any>>] => {
  const [makeRequest] = useLazyFetch(entityClient);

  return [makeRequest];
};
