import { useCallback, useContext, useState, useEffect } from 'react';
import PropTypes from 'prop-types';
import { useReducerAsync } from 'use-reducer-async';
import { EntityContext } from '@/hooks/useNewEntity';
import { Table, THead, TBody, TH, TR } from '@/components/Table';
import generateTestIds from '@/helpers/generateTestIds';
import RemoveConfirmationModal from '@/components/RemoveConfirmationModal';
import { ACTIONS, asyncActionHandlers, entitiesReducer } from '@/reducers/entitiesReducer';
import EntityRows from './EntityRows';

// New entity effect (ms)
const NEW_ENTITY_EFFECT_MS = 2 * 1000;

export const testIds = generateTestIds('entities_table', []);

function EntitiesTable({ attrName, attrValue, namespace, isViewEntityMode }) {
  const { newEntity, setNewEntity } = useContext(EntityContext);
  const [entityToDelete, setEntityToDelete] = useState('');
  const [entities, dispatch] = useReducerAsync(entitiesReducer, [], asyncActionHandlers);

  const attributeURI = `${namespace}/attr/${attrName}/value/${attrValue}`;

  useEffect(() => {
    dispatch({
      type: ACTIONS.FETCH,
      name: attrName,
      value: attrValue,
      namespace,
    });
  }, [attrName, attrValue, namespace, dispatch]);

  // Show color for limited time
  useEffect(() => {
    if (newEntity) {
      setTimeout(() => setNewEntity(), NEW_ENTITY_EFFECT_MS);
    }
  }, [newEntity, setNewEntity]);

  const restore = useCallback(
    (dn) => {
      dispatch({
        type: ACTIONS.ASSIGN,
        attributeURI,
        entityId: dn,
      });
    },
    [attributeURI, dispatch]
  );

  const unassign = useCallback(() => {
    setEntityToDelete('');
    dispatch({
      type: ACTIONS.DELETE,
      attributeURI,
      entityId: entityToDelete,
    });
  }, [attributeURI, dispatch, entityToDelete]);

  const cancel = useCallback(() => {
    setEntityToDelete('');
  }, []);

  return (
    <div data-testid={testIds._}>
      <Table>
        <THead>
          <TR>
            <TH>Common Name</TH>
            <TH>Email</TH>
            <TH>Type</TH>
            <TH>Distinguished Name</TH>
            <TH>Actions</TH>
          </TR>
        </THead>
        <TBody>
          {entities &&
            entities.map(({ userId, ...props }) => {
              return (
                <EntityRows
                  {...props}
                  newEntity={newEntity === userId}
                  userId={userId}
                  key={userId}
                  setEntityToDelete={setEntityToDelete}
                  restore={restore}
                  isViewEntityMode={isViewEntityMode}
                />
              );
            })}
        </TBody>
      </Table>
      {entityToDelete ? (
        <RemoveConfirmationModal
          title={`Remove attribute from "${entityToDelete}"?`}
          onRemove={unassign}
          onCancel={cancel}
        >
          {`Removing “${attrName}:${attrValue}" may affect what data this entity can access. Would you still like to remove this attribute?`}
        </RemoveConfirmationModal>
      ) : null}
    </div>
  );
}

EntitiesTable.propTypes = {
  attrName: PropTypes.string,
  attrValue: PropTypes.string,
  namespace: PropTypes.string,
  isViewEntityMode: PropTypes.bool,
};

EntitiesTable.defaultProps = {
  attrName: '',
  attrValue: '',
  namespace: '',
  isViewEntityMode: false,
};

export default EntitiesTable;
