import React, { useContext } from 'react';
import PropTypes from 'prop-types';
import { TR, TD } from '@/components/Virtruoso';
import { generateTestIds } from '@/helpers';
import { EntityContext } from '@/hooks/useNewEntity';
import { propTypes as entityPropTypes } from '@/models/Entity';
import useAssignEntityToAttribute, {
  STATES as AssignEntityToAttributeStates,
} from '../hooks/useAssignEntityToAttribute';

import styles from './EntityRow.module.css';

export const testIds = generateTestIds('attribute_entity_assigner--entity_row', [
  'name',
  'email',
  'type',
  'userId',
  'action',
  'assignAction',
]);

function EntityRow({ namespace, attributeName, attributeValue, entity, onSuccess }) {
  const { setNewEntity } = useContext(EntityContext);
  const { setEntityId, state } = useAssignEntityToAttribute(
    namespace,
    attributeName,
    attributeValue,
    { onSuccess }
  );
  const { userId, name, email, type } = entity;

  function renderRowAction() {
    if (entity.hasAttribute(namespace, attributeName, attributeValue)) {
      return <span className={styles.assigned}>Already assigned</span>;
    }
    if (state === AssignEntityToAttributeStates.LOADING) {
      return <span className={styles.assigned}>Saving...</span>;
    }
    if (state === AssignEntityToAttributeStates.SUCCESS) {
      return <span className={styles.assigned}>Assigned</span>;
    }
    if (state === AssignEntityToAttributeStates.FAILURE) {
      // No design exists
    }
    return (
      <button
        type="button"
        className={styles.unassigned}
        onClick={() => {
          setEntityId(userId);
          setNewEntity(userId);
        }}
        data-testid={testIds.assignAction}
      >
        Assign to Attribute
      </button>
    );
  }

  return (
    <TR key={userId} data-testid={testIds._}>
      <TD data-testid={testIds.name}>{name}</TD>
      <TD data-testid={testIds.email}>{email}</TD>
      <TD data-testid={testIds.type}>{type}</TD>
      <TD data-testid={testIds.userId}>{userId}</TD>
      <TD style={{ textAlign: 'right' }} data-testid={testIds.action}>
        {renderRowAction()}
      </TD>
    </TR>
  );
}

EntityRow.propTypes = {
  attributeName: PropTypes.string.isRequired,
  attributeValue: PropTypes.string.isRequired,
  entity: PropTypes.shape(entityPropTypes).isRequired,
  namespace: PropTypes.string.isRequired,
  onSuccess: PropTypes.func,
};

EntityRow.defaultProps = {
  onSuccess: () => {},
};

export default EntityRow;
