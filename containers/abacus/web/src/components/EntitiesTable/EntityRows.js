import React, { useCallback, useEffect, useContext } from 'react';
import PropTypes from 'prop-types';
import { TD, TR } from '@/components/Table';
import LinkButton from '@/components/LinkButton';
import { EntityContext } from '@/hooks/useNewEntity';
import { useRouter } from 'next/router';

const TYPE_NPE = 'NPE';
const TYPE_PERSON = 'Person';

const renderTD = (styles, text) => (
  <TD>
    <span style={{ styles }}>{text}</span>
  </TD>
);

const EntitiesRow = ({
  name,
  email,
  nonPersonEntity,
  userId: dn,
  isDeleted,
  setEntityToDelete,
  restore,
  loading,
  isViewEntityMode,
  newEntity,
}) => {
  const type = nonPersonEntity ? TYPE_NPE : TYPE_PERSON;
  const textDecoration = isDeleted ? 'line-through' : 'none';
  const router = useRouter();
  const defaultButtonText = isDeleted ? 'Restore' : 'Remove entity from attribute';
  const buttonText = isViewEntityMode ? 'Attributes & details' : defaultButtonText;
  const restoreEntity = useCallback(() => restore(dn), [dn, restore]);
  const deleteEntity = useCallback(() => setEntityToDelete(dn), [dn, setEntityToDelete]);
  const viewEntity = useCallback(() => router.push(`/entities/${dn}`), [dn, router]);
  const { setNewEntity } = useContext(EntityContext);
  const defaultAction = isDeleted ? restoreEntity : deleteEntity;

  useEffect(() => {
    return () => {
      setNewEntity('');
    };
  });

  return (
    <TR newEntity={newEntity} key={dn}>
      {renderTD(textDecoration, name)}
      {renderTD(textDecoration, email)}
      {renderTD(textDecoration, type)}
      {renderTD(textDecoration, dn)}
      <TD>
        {loading ? (
          <span>Saving...</span>
        ) : (
          <>
            {isViewEntityMode && <LinkButton text={buttonText} onClick={viewEntity} />}
            {!isViewEntityMode && <LinkButton text={buttonText} onClick={defaultAction} />}
          </>
        )}
      </TD>
    </TR>
  );
};

EntitiesRow.propTypes = {
  name: PropTypes.string,
  email: PropTypes.string,
  nonPersonEntity: PropTypes.bool,
  userId: PropTypes.string,
  isDeleted: PropTypes.bool,
  loading: PropTypes.bool,
  setEntityToDelete: PropTypes.func,
  restore: PropTypes.func,
  isViewEntityMode: PropTypes.bool,
  newEntity: PropTypes.bool,
};

EntitiesRow.defaultProps = {
  name: 'N/A',
  email: 'N/A',
  nonPersonEntity: false,
  userId: '',
  isDeleted: false,
  loading: false,
  setEntityToDelete: () => {},
  restore: () => {},
  isViewEntityMode: false,
  newEntity: false,
};

export default EntitiesRow;
