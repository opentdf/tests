import React, { useState } from 'react';
import PropTypes from 'prop-types';
import generateTestIds from '@/helpers/generateTestIds';
import { Button, Input } from '@/components/Virtruoso';

import styles from './SearchEntities.module.css';

export const testIds = generateTestIds('attribute_entity_assigner--search_entities', [
  'input',
  'button',
]);

function SearchEntities({ onSearch, isSearching }) {
  const [searchQuery, setSearchQuery] = useState();
  return (
    <div data-testid={testIds._}>
      <div className={styles.label}>Search for an entity</div>
      <div className={styles.searchContainer}>
        <div className={styles.searchInput}>
          <Input
            message="Entity name, email, or distinguished name"
            state={Input.STATE.INFO}
            onChange={(e) => setSearchQuery(e.target.value)}
            data-testid={testIds.input}
          />
        </div>
        <div styles={styles.searchAction}>
          <Button
            variant={Button.VARIANT.PRIMARY}
            size={Button.SIZE.MEDIUM}
            disabled={isSearching || !searchQuery}
            onClick={() => !isSearching && onSearch(searchQuery)}
            data-testid={testIds.button}
          >
            {isSearching ? '...' : 'Search'}
          </Button>
        </div>
      </div>
    </div>
  );
}

SearchEntities.propTypes = {
  onSearch: PropTypes.func.isRequired,
  isSearching: PropTypes.bool,
};

SearchEntities.defaultProps = {
  isSearching: false,
};

export default SearchEntities;
