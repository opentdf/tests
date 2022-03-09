import {useCallback, useEffect, useMemo, useState} from "react";
import {useHistory} from "react-router";
import {Divider} from "antd";

import {getCancellationConfig, keyCloakClient} from "../../service";
import {routes} from "../../routes";
import ClientsTable from "./ClientsTable";
import UsersTable from "./UsersTable";

import "./Entitlements.css";
import {components} from "../../keycloak";
import {keycloakConfig} from "../../config";

const Entitlements = () => {
  const history = useHistory();
  const [clients, setClients] = useState([]);
  const [users, setUsers] = useState([]);

  useEffect(() => {
    const { token, cancel } = getCancellationConfig();

    keyCloakClient
      .get(`/admin/realms/${keycloakConfig.realm}/clients`, {
        cancelToken: token,
      })
      .then((res) => {
          const clientsWithMapper = res.data.filter((element: components["schemas"]["ClientRepresentation"]) => {
              return element.protocolMappers?.find((pm => pm.protocolMapper === 'virtru-oidc-protocolmapper'));
          })
          setClients(clientsWithMapper);
      });

    keyCloakClient
      .get(`/admin/realms/${window.SERVER_DATA.realms}/users`, {
        cancelToken: token,
      })
      .then((res) => {
        setUsers(res.data);
      });

    return () => {
      cancel("Operation canceled by the user.");
    };
  }, []);

  const onClientRecordClick = useCallback(
    (id) => {
      history.push(`${routes.CLIENTS}/${id}`);
    },
    [history],
  );

  const onUserRecordClick = useCallback(
    (id) => {
      history.push(`${routes.USERS}/${id}`);
    },
    [history],
  );

  const formattedClients = useMemo(
    () =>
      clients.map(({ clientId, id, enabled }) => ({ clientId, id, enabled })),
    [clients],
  );

  const formattedUsers = useMemo(
    () => users.map(({ username, id, enabled }) => ({ username, id, enabled })),
    [users],
  );

  return (
    <section>
      <ClientsTable
        data={formattedClients}
        loading={!clients.length}
        onRowClick={onClientRecordClick}
      />

      <Divider />

      <UsersTable
        data={formattedUsers}
        loading={!users.length}
        onRowClick={onUserRecordClick}
      />
    </section>
  );
};

export default Entitlements;
