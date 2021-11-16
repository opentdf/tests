import { useEffect, useMemo, useState } from "react";
import { useFetch } from ".";
import { entityClient } from "../service";
import { Attribute } from "../types/attributes";
import { EntityAttribute } from "../types/entitlements";
import { Method } from "../types/enums";

export const useAttributes = (entityId: string) => {
  const [attributes, setAttributes] = useState<EntityAttribute[]>([]);

  const [data] = useFetch<EntityAttribute[]>(entityClient, { method: Method.GET, path: `/attributes/v1/attrName/${entityId}/attribute` });

  useEffect(() => {
    console.log(`data`, data);
    if (data) {
      setAttributes(data);
    }

  }, [data]);

  return { attributes };
};

export const useAttrs = (namespace: string) => {
  const [attrs, setAttrs] = useState<Attribute[]>([]);


  const config = useMemo(() => ({ method: Method.POST, path: `/attributes/v1/attrName`, params: { namespace } }), [namespace]);

  const [data] = useFetch<Attribute[]>(
    entityClient,
    config
  );

  useEffect(() => {
    if (data) {
      setAttrs(data);
    }

  }, [data]);

  return { attrs };

};
