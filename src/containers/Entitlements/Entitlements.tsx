import { useCallback, useEffect, useMemo, useState } from "react";
import { useHistory } from "react-router";
import { Divider } from "antd";

import { getCancellationConfig, keyCloakClient } from "../../service";
import ClientsTable from "./ClientsTable";
import UsersTable from "./UsersTable";

import "./Entitlements.css";
import { routes } from "../../routes";

const Entitlements = () => {
  const history = useHistory();
  const [clients, setClients] = useState([]);
  const [users, setUsers] = useState([]);

  useEffect(() => {
    const { token, cancel } = getCancellationConfig();

    keyCloakClient
      .get(`/admin/realms/tdf/clients`, { cancelToken: token })
      .then((res) => {
        setClients(res.data);
      });

    keyCloakClient
      .get(`/admin/realms/tdf/users`, { cancelToken: token })
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
        loading={!!!clients.length}
        onRowClick={onClientRecordClick}
      />

      <Divider />

      <UsersTable
        data={formattedUsers}
        loading={!!!users.length}
        onRowClick={onUserRecordClick}
      />
    </section>
  );
};

export default Entitlements;
