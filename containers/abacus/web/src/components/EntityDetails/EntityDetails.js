import React, { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import EntityCard from '@/components/EntityCard/EntityCard';
import useNsAttrValMap from '@/hooks/useNsAttrValMap';

import styles from './EntityDetails.module.css';

const renderAttributeCards = ({ list, lastAssigned, deleteEntity, deletedList, assignEntity }) =>
  list
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([name, { order, authorityNamespace }]) => (
      <div key={name} className={styles.item}>
        <EntityCard
          name={name}
          authorityNamespace={authorityNamespace}
          values={order}
          selectedValue={lastAssigned}
          deleteEntity={deleteEntity}
          assignEntity={assignEntity}
          deletedList={deletedList}
        />
      </div>
    ));

function EntityDetails({
  selectedNamespace,
  attributes,
  lastAssigned,
  deleteEntity,
  deletedList,
  assignEntity,
}) {
  const [list, setList] = useState([]);
  // we show both
  const map = useNsAttrValMap(attributes, deletedList);

  useEffect(() => {
    setList(Object.entries(map[selectedNamespace] || []));
  }, [map, selectedNamespace]);

  return (
    <div className={styles.container}>
      {renderAttributeCards({ list, lastAssigned, deleteEntity, deletedList, assignEntity })}
    </div>
  );
}

EntityDetails.displayName = 'EntityDetails';

EntityDetails.propTypes = {
  deleteEntity: PropTypes.func,
  assignEntity: PropTypes.func,
  selectedNamespace: PropTypes.string,
  deletedList: PropTypes.instanceOf(Set),
  lastAssigned: PropTypes.string,
  attributes: PropTypes.arrayOf(PropTypes.string),
};

EntityDetails.defaultProps = {
  deleteEntity: () => {},
  assignEntity: () => {},
  deletedList: new Set(),
  selectedNamespace: '',
  lastAssigned: '',
  attributes: [],
};

export default React.memo(EntityDetails);
