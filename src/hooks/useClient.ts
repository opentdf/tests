import { useEffect, useState } from "react";
import { useFetch } from ".";
import { keyCloakClient } from "../service";
import { Method } from "../types/enums";
import { Client } from "../types/keycloak";


export const useClient = (id: string) => {
  const [client, setClient] = useState<Client>({});

  const [data] = useFetch<Client>(keyCloakClient, {
    method: Method.GET,
    path: `/admin/realms/${window.SERVER_DATA.realm}/clients/${id}`
  });

  useEffect(() => {
    if (data) {
      setClient(data);
    }
  }, [data]);

  return { client };
};
