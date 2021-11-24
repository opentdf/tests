import { useCallback, useContext, useEffect, useMemo } from 'react';
import { useRouter } from 'next/router';
import Page from '@/components/Page';
import generateTestIds from '@/helpers/generateTestIds';
import { ClientsTable, UsersTable } from '@/components/KeyCloakTable';
import { KeyCloakContext, KEYCLOAK_ACTIONS } from '@/hooks/useKeyCloak';

const VIRTU_PROTOCOL = 'virtru-oidc-protocolmapper';

export const testIds = generateTestIds('attributes-page', ['selector']);

export default function AttributesPage() {
  const [state, dispatch, keyCloak] = useContext(KeyCloakContext);
  const router = useRouter();

  const filteredClients = useMemo(
    () =>
      state?.clients?.filter((client) =>
        client.protocolMappers?.some(
          (protocolMap) => protocolMap?.protocolMapper === VIRTU_PROTOCOL
        )
      ),
    [state?.clients]
  );

  useEffect(() => {
    if (keyCloak.authenticated) {
      dispatch({ type: KEYCLOAK_ACTIONS.GET_CLIENTS });
      dispatch({ type: KEYCLOAK_ACTIONS.GET_USERS });
    }
  }, [dispatch, keyCloak?.authenticated]);

  const onUserRowClick = useCallback(
    (record) => {
      router.push(`entities/users/${record.id}`);
    },
    [router]
  );

  const onClientRowClick = useCallback(
    (record) => {
      router.push(`entities/clients/${record.id}`);
    },
    [router]
  );

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      actionAlignment={Page.ACTION_ALIGNMENTS.RIGHT}
      title="Entity"
      description="A person, organization, device, or process who will access data based on their attributes."
    >
      <Page.Breadcrumb text="Entities" />
      <ClientsTable
        loading={!filteredClients}
        data={filteredClients}
        onRowClick={onClientRowClick}
      />
      <UsersTable loading={!state.users} data={state?.users} onRowClick={onUserRowClick} />
    </Page>
  );
}
