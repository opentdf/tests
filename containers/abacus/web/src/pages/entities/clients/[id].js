import { useCallback, useContext, useEffect, useState } from 'react';
import { useRouter } from 'next/router';
import { useReducerAsync } from 'use-reducer-async';
import { Table, Divider } from 'antd';
import { ToastContainer } from 'react-toastify';
import Page from '@/components/Page';
import { KEYCLOAK_ACTIONS, KeyCloakContext } from '@/hooks/useKeyCloak';
import EntityAttributeAssigner from '@/components/EntityAttributeAssigner';
import useAttributeRules from '@/hooks/useAttributeRules';
import useClientAttributesTable from '@/hooks/useClientAttributesTable';

import getAttributeUri from '@/helpers/getAttributeUri';
import { ACTIONS, asyncActionHandlers, entitiesReducer } from '@/reducers/entitiesReducer';
import useAuthorityNamespaces from '@/hooks/useAuthorityNamespaces';
import 'react-toastify/dist/ReactToastify.css';
import 'antd/dist/antd.css';

const ClientPage = () => {
  const [entities, dispatch] = useReducerAsync(entitiesReducer, [], asyncActionHandlers);
  const router = useRouter();
  const { id } = router.query;
  const authorityNamespaces = useAuthorityNamespaces();
  const [selectedNamespace, setSelectedNamespace] = useState('');
  const attributeRules = useAttributeRules(selectedNamespace);
  const [state, sendAction, keyCloak] = useContext(KeyCloakContext);
  const [attributes, setAttributes] = useState([]);
  const [isLoading] = useState(false);

  const onDelete = useCallback(
    ({ attribute, entityId }) => {
      dispatch({
        type: ACTIONS.DELETE,
        attributeURI: attribute,
        entityId,
      });
    },
    [dispatch]
  );

  const { dataSource, columns } = useClientAttributesTable(entities, onDelete);

  useEffect(() => {
    return function cleanup() {
      sendAction({ type: KEYCLOAK_ACTIONS.CLEAN_UP });
    };
  }, [sendAction]);

  useEffect(() => {
    if (keyCloak.authenticated) {
      sendAction({ type: KEYCLOAK_ACTIONS.GET_CLIENT, id });
    }
  }, [id, keyCloak.authenticated, sendAction]);

  const [entityId, setEntityId] = useState('');
  useEffect(() => {
    if (keyCloak.authenticated && entityId) {
      dispatch({
        type: ACTIONS.FETCH,
        entityId,
      });
    }
  }, [dispatch, entityId, keyCloak.authenticated]);

  useEffect(() => {
    const selectedEntity = state?.client?.clientId
      ? `service-account-${state.client.clientId}`
      : '';

    if (selectedEntity) {
      setEntityId(selectedEntity);
    }
  }, [state]);

  useEffect(() => {
    setAttributes(
      entities.filter((entity) => entity.entityId === entityId).map((entity) => entity.attribute)
    );
  }, [entities, entityId]);

  const assignEntity = useCallback(
    ({ ns, attr, val }) => {
      const attributeURI = getAttributeUri({ ns, attr, val });

      dispatch({
        type: ACTIONS.ASSIGN,
        attributeURI,
        entityId,
      });
    },
    [dispatch, entityId]
  );

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      actionAlignment={Page.ACTION_ALIGNMENTS.RIGHT}
      title="Entity"
      description="A person, organization, device, or process who will access data based on their attributes."
    >
      <Page.Breadcrumb text="Entities" />

      {id && (
        <EntityAttributeAssigner
          ns={selectedNamespace}
          authorityNamespaces={authorityNamespaces}
          setSelectedNamespace={setSelectedNamespace}
          rules={attributeRules}
          attributes={attributes}
          isLoading={isLoading}
          assign={assignEntity}
        />
      )}

      {entities.length && (
        <>
          <Table dataSource={dataSource} columns={columns} pagination={false} bordered />
          <Divider />
        </>
      )}

      <div>
        <h2>{`Client ${id}`}</h2>
        <pre>{JSON.stringify(state.client, null, 2)}</pre>
      </div>
      <ToastContainer />
    </Page>
  );
};

export default ClientPage;
