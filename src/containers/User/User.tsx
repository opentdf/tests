import {useCallback, useEffect, useMemo, useState} from "react";
import { Divider } from "antd";
import { useParams } from "react-router";
import {entitlementsClient, getCancellationConfig, keyCloakClient} from "../../service";
import { toast } from "react-toastify";
import {useEntitlements} from "../Client/hooks/useEntitlement";
import {Method} from "../../types/enums";
import AssignAttributeForm from "../Client/AssignAttributeForm";
import ClientTable from "../Client/ClientTable";
import {TableData} from "../../types/table";
import {keycloakConfig} from "../../config";

const User = () => {
    const {id} = useParams<{ id: string }>();

    const [user, setUser] = useState();

    useEffect(() => {
        const {token, cancel} = getCancellationConfig();

    keyCloakClient
      .get(`/admin/realms/${keycloakConfig.realm}/users/${id}`, {
        cancelToken: token,
      })
      .then((res) => {
        setUser(res.data);
      })
      .catch((error) => toast.error(error));

        return () => {
            cancel("Operation canceled by the user.");
        };
    }, [id]);

    // WIP
    const {
        getEntitlements,
        data: entityAttributes,
        loading,
    } = useEntitlements();
    const [entityId, setEntityId] = useState(id);

    const config = useMemo(
        () => ({
            method: Method.GET,
            path: `/entitlements`,
            params: {params: {entityId}},
        }),
        [entityId],
    );
    const onAssignAttribute = useCallback(() => {
        const config = {
            method: Method.GET,
            path: `/entitlements`,
            params: {params: {entityId}},
        };

        getEntitlements(config);
    }, [entityId, getEntitlements]);
    useEffect(() => {
        getEntitlements(config);
    }, [config, getEntitlements]);

    useEffect(() => {
        setEntityId(id);
    }, [id]);

    const clientTableData = useMemo(
        () =>
            entityAttributes?.reduce((acc: TableData[], item): TableData[] => {
                const transformedItem = Object.entries(item).flatMap(([key, values]) =>
                    values.map((value) => ({
                        attribute: key,
                        entityId: value,
                    })),
                );

                return [...acc, ...transformedItem];
            }, []),
        [entityAttributes],
    );

    const onDeleteKey = useCallback(
        (entity: TableData) => {
            entitlementsClient
                .delete(`/entitlements/${entity.attribute}`, {
                    data: [entity.entityId],
                })
                .then(() => getEntitlements(config));
        },
        [config, getEntitlements],
    );

    return (
        <section>
            <AssignAttributeForm
                entityId={entityId}
                onAssignAttribute={onAssignAttribute}
            />

            <Divider/>

            <h2>User {id}</h2>
            <ClientTable
                onDeleteKey={onDeleteKey}
                data={clientTableData}
                loading={loading}
            />

            <Divider/>

            <pre>{JSON.stringify(user, null, 2)}</pre>
        </section>
    );
};

export default User;
