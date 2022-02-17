import { Divider } from "antd";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { entityClient } from "../../service";
import AssignAttributeForm from "./AssignAttributeForm";
import ClientTable from "./ClientTable";
import { useEntitlements } from "./hooks/useEntitlement";
import { useClient } from "../../hooks";
import { Method } from "../../types/enums";

// @ts-ignore
const {entitlements} = window.SERVER_DATA;

const Client = () => {
  const { id } = useParams<{ id: string }>();

  const [entityId, setEntityId] = useState(id);

  const { client } = useClient(id);
  const {
    getEntitlements,
    data: entityAttributes,
    loading,
  } = useEntitlements();

  useEffect(() => {
    const config = {
      method: Method.GET,
      path: entitlements + `/entitlements?entityId=${entityId}`,
    };

    getEntitlements(config);
  }, [entityId, getEntitlements]);

  useEffect(() => {
    setEntityId(`${id}`);
  }, [id]);

  const onDeleteKey = useCallback(
    (attribute) => {
      entityClient.delete(
          entitlements + `/entitlements/${entityId}`, attribute
      );
    },
    [entityId],
  );

  const onAssignAttribute = useCallback(() => {
    const config = {
      method: Method.GET,
      path: entitlements + `/entitlements?entityId=${entityId}`,
    };

    getEntitlements(config);
  }, [entityId, getEntitlements]);

  // @ts-ignore
  return (
    <section>
      <AssignAttributeForm
        entityId={entityId}
        onAssignAttribute={onAssignAttribute}
      />

      <Divider />

      <Divider />

      <article>
        <h2>User {id}</h2>

        <ClientTable
          onDeleteKey={onDeleteKey}
          // entityAttributes={entityAttributes}
          loading={loading}
        />
        <Divider />

        <pre>{JSON.stringify(client, null, 2)}</pre>
      </article>
    </section>
  );
};

export default Client;
