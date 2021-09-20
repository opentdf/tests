import React, { useState } from 'react';
import PropTypes from 'prop-types';
import { generateTestIds } from '@/helpers';
import { Table, TBody } from '@/components/Virtruoso';
import useSearchEntities, { STATES as SEARCH_ENTITIES_STATE } from './hooks/useSearchEntities';
import EntityRow from './components/EntityRow';
import SearchEntities from './components/SearchEntities';

import styles from './AttributeEntityAssigner.module.css';

export const testIds = generateTestIds('attribute_entity_assigner', [
  'search',
  'table',
  'tableLabel',
]);

function renderEntityTable(namespace, attributeName, attributeValue, entities, onSuccess) {
  if (!Array.isArray(entities)) {
    return null;
  }
  const label = `Found ${entities.length} entities`;
  return (
    <div className={styles.itemGroup}>
      <div className={styles.label} data-testid={testIds.tableLabel}>
        {label}
      </div>
      <Table data-testIds={testIds.table}>
        <TBody>
          {entities.map((entity) => (
            <EntityRow
              key={entity.userId}
              entity={entity}
              namespace={namespace}
              attributeName={attributeName}
              attributeValue={attributeValue}
              onSuccess={onSuccess}
            />
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function AttributeEntityAssigner({ namespace, attributeName, attributeValue, onSuccess }) {
  const [searchQuery, setSearchQuery] = useState('');
  const { entities, state: searchEntitiesState } = useSearchEntities(searchQuery);

  // If the search entities is in a loading state
  const isSearching = searchEntitiesState === SEARCH_ENTITIES_STATE.LOADING;

  return (
    <div data-testid={testIds._}>
      <div className={styles.itemGroup} data-testid={testIds.search}>
        <SearchEntities onSearch={setSearchQuery} isSearching={isSearching} />
      </div>
      {renderEntityTable(namespace, attributeName, attributeValue, entities, onSuccess)}
    </div>
  );
}

AttributeEntityAssigner.propTypes = {
  attributeName: PropTypes.string.isRequired,
  attributeValue: PropTypes.string.isRequired,
  namespace: PropTypes.string.isRequired,
  onSuccess: PropTypes.func,
};

AttributeEntityAssigner.defaultProps = {
  onSuccess: () => {},
};

export default AttributeEntityAssigner;
