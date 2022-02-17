import { useEffect, useState } from "react";
import { useFetch } from "./useFetch";
import { entityClient } from "../service";
import { Authorities } from "../types/attributes";
import { Method } from "../types/enums";

// @ts-ignore
const serverData = window.SERVER_DATA;

export const useAuthorities = () => {
  const [authorities, setAuthorities] = useState<Authorities>([]);

  const [data] = useFetch<Authorities>(entityClient, { method: Method.GET, path: serverData.attributes + `/authorities` });

  useEffect(() => {
    if (data) {
      setAuthorities(data);
    }

  }, [data]);

  return authorities;
};
