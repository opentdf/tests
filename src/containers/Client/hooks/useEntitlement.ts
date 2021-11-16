import { AxiosResponse } from "axios";
import { useEffect, useState } from "react";
import { useFetch } from "../../../hooks";
import { Config, useLazyFetch } from "../../../hooks/useFetch";
import { entityClient } from "../../../service";
import { EntityAttribute } from "../../../types/entitlements";
import { Method } from "../../../types/enums";

export const useEntitlements = (entityId: string) => {
  const [entityAttributes, setEntityAttributes] = useState<EntityAttribute[]>([]);

  const [data] = useFetch<EntityAttribute[]>(entityClient, { method: Method.GET, path: `/entitlement/v1/entity/${entityId}/attribute` });


  useEffect(() => {
    if (data) {
      setEntityAttributes(data);
    }

  }, [data]);

  return { entityAttributes };
};

export const useUpdateEntitlement = (): [(config: Config) => Promise<AxiosResponse<any, any>>] => {
  const [makeRequest] = useLazyFetch(entityClient);

  return [makeRequest];
};
