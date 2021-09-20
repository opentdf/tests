import React, { useEffect, useState } from 'react';
import { Button } from '@/components/Virtruoso';
import Page from '@/components/Page';
import { useRouter } from 'next/router';
import EntityDetails from '@/components/EntityDetails';
import useAuthorityNamespaces from '@/hooks/useAuthorityNamespaces';
import useAttributeRules from '@/hooks/useAttributeRules';
import { ACTIONS, asyncActionHandlers, entitiesReducer } from '@/reducers/entitiesReducer';
import AuthorityNamespaceSelector from '@/components/AuthorityNamespaceSelector';
import EntityAttributeAssigner from '@/components/EntityAttributeAssigner';
import RemoveConfirmationModal from '@/components/RemoveConfirmationModal';
import { useReducerAsync } from 'use-reducer-async';
import getAttributeUri from '@/helpers/getAttributeUri';

export default function AttributesPage() {
  const [entity, setEntity] = useState(null);
  const [attributes, setAttributes] = useState([]);
  const [isAssignMode, setIsAssignMode] = useState(false);
  const [selectedNamespace, setSelectedNamespace] = useState('');
  const [lastAssigned, setLastAssigned] = useState('');

  const [attributeToDelete, setAttributeToDelete] = useState(null);
  const [attributeToAssign, setAttributeToAssign] = useState(null);

  const [deletedAttributes, setDeletedAttributes] = useState(new Set());
  const [isLoading, setIsLoading] = useState(false);

  const routePath = useRouter();
  const { entityId } = routePath.query;

  const authorityNamespaces = useAuthorityNamespaces();
  const attributeRules = useAttributeRules(selectedNamespace);
  const [entities, dispatch] = useReducerAsync(entitiesReducer, [], asyncActionHandlers);

  const inactivateEntity = () => {
    dispatch({
      type: ACTIONS.INACTIVATE_ENTITY,
      entity,
    });
  };

  const assignEntity = ({ ns, attr, val }) => {
    const attributeURI = getAttributeUri({ ns, attr, val });
    setAttributeToAssign(attributeURI);

    dispatch({
      type: ACTIONS.ASSIGN,
      attributeURI,
      entityId,
    });
  };

  const deleteEntity = ({ ns, attr, val }) => {
    const attributeURI = getAttributeUri({ ns, attr, val });

    dispatch({
      type: ACTIONS.DELETE,
      attributeURI,
      entityId,
    });
  };

  const cancel = () => {
    setIsAssignMode(false);
  };

  useEffect(() => {
    dispatch({
      type: ACTIONS.FETCH,
    });
  }, [dispatch]);

  useEffect(() => {
    if (!entity) {
      return;
    }

    setIsLoading((prevLoading) => {
      const isUpdated = prevLoading && !entity.loading;
      const isDeleted = isUpdated && attributeToDelete;
      const isAssigned = isUpdated && attributeToAssign;
      const isRestored = isAssigned && deletedAttributes.has(attributeToAssign);

      if (!isDeleted && !isAssigned) {
        return entity.loading;
      }

      if (isDeleted) {
        const newDeletedSet = new Set([...deletedAttributes, getAttributeUri(attributeToDelete)]);
        setAttributeToDelete(null);
        setDeletedAttributes(newDeletedSet);
        setAttributes([...attributes.filter((attr) => !newDeletedSet.has(attr))]);
      } else if (isAssigned && !isRestored) {
        setLastAssigned(attributeToAssign);
        setAttributeToAssign(null);
      } else if (isRestored) {
        const newDeletedSet = new Set([...deletedAttributes]);
        newDeletedSet.delete(attributeToAssign);
        setDeletedAttributes(newDeletedSet);
      }

      if (isAssigned) {
        setIsAssignMode(false);
        setAttributes([...attributes, attributeToAssign]);
      }

      return entity.loading;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entity]);

  useEffect(() => {
    if (!entities) {
      return;
    }
    const selectedEntity = entities.find(({ userId }) => userId === entityId);
    if (!selectedEntity) {
      return;
    }

    setEntity((prevEntity) => {
      if (!prevEntity) {
        setAttributes([...selectedEntity.attributes]);
      }

      return selectedEntity;
    });
  }, [entities, entityId]);

  const landingTitle =
    entity && !entity.nonPersonEntity
      ? `${(entity && entity.name) || ''}’s attributes`
      : 'Entity attributes';

  const assignTitle = `Assign attribute to ${(entity && entity.name) || ''}`;

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      actions={[
        {
          key: 'edit',
          children: (
            <Button variant={Button.VARIANT.SECONDARY} size={Button.SIZE.MEDIUM}>
              Edit
            </Button>
          ),
        },
        {
          key: 'delete',
          children: (
            <Button
              variant={Button.VARIANT.NO_OUTLINE}
              size={Button.SIZE.MEDIUM}
              onClick={() => inactivateEntity()}
            >
              Delete
            </Button>
          ),
        },
      ]}
      entityValues={entity}
      actionAlignment={Page.ACTION_ALIGNMENTS.LEFT}
      title="Entity"
      contentTitle={isAssignMode ? assignTitle : landingTitle}
      titleActions={[
        {
          key: 'assign',
          children: !isAssignMode ? (
            <Button
              variant={Button.VARIANT.PRIMARY}
              size={Button.SIZE.SMALL}
              onClick={() => setIsAssignMode(true)}
            >
              Assign attribute
            </Button>
          ) : null,
        },
      ]}
      description="A person, organization, device, or process who will access data based on their attributes."
    >
      <Page.Breadcrumb text="Entities" href="/entities" />
      <Page.Breadcrumb text={entity && !entity.nonPersonEntity ? 'Person' : 'Non-Person Entity'} />
      {!isAssignMode && entity && entity.fetching && 'Loading...'}

      {!isAssignMode && entity && !entity.fetching && (
        <>
          <AuthorityNamespaceSelector
            selectedNamespace={selectedNamespace}
            setSelectedNamespace={setSelectedNamespace}
            authorityNamespaces={authorityNamespaces}
          />
          <EntityDetails
            selectedNamespace={selectedNamespace}
            entityId={entityId}
            attributes={attributes}
            lastAssigned={lastAssigned}
            deletedList={deletedAttributes}
            deleteEntity={setAttributeToDelete}
            assignEntity={assignEntity}
          />
        </>
      )}

      {isAssignMode && (
        <EntityAttributeAssigner
          ns={selectedNamespace}
          authorityNamespaces={authorityNamespaces}
          setSelectedNamespace={setSelectedNamespace}
          rules={attributeRules}
          attributes={attributes}
          isLoading={isLoading}
          assign={assignEntity}
          cancel={cancel}
        />
      )}

      {attributeToDelete && (
        <RemoveConfirmationModal
          title={`Remove "${attributeToDelete.attr}:${attributeToDelete.val}" from entity?`}
          onRemove={() => {
            deleteEntity(attributeToDelete);
          }}
          loading={isLoading}
          onCancel={() => {
            setAttributeToDelete(null);
          }}
        >
          {`Removing this attribute may affect what data ${entity.name} can access. Would you still like to remove this attribute?`}
        </RemoveConfirmationModal>
      )}
    </Page>
  );
}
