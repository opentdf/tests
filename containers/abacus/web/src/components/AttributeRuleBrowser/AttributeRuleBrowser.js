import React from 'react';
import PropTypes from 'prop-types';
import useAttributeRules from '@/hooks/useAttributeRules';
import { generateTestIds } from '@/helpers';
import AttributeRuleCard from '../AttributeRuleCard';

import styles from './AttributeRuleBrowser.module.css';

export const testIds = generateTestIds('attribute_rule_browser', ['card']);

// TODO finish when ready
function handleDetailsAction() {}
function handleEditRuleAction() {}
function handleNewValueAction() {}

export function renderAttributeCards(attributeRules) {
  if (!Array.isArray(attributeRules)) {
    return null;
  }

  return attributeRules.map(({ authorityNamespace, name, rule, order }) => {
    return (
      <div key={name} className={styles.item} data-testid={testIds.card}>
        <AttributeRuleCard
          name={name}
          accessType={rule}
          authorityNamespace={authorityNamespace}
          values={order}
          onDetailsAction={handleDetailsAction}
          onEditRuleAction={handleEditRuleAction}
          onNewValueAction={handleNewValueAction}
        />
      </div>
    );
  });
}

function AttributeRuleBrowser({ selectedNamespace }) {
  const attributeRules = useAttributeRules(selectedNamespace);

  return (
    <div className={styles.container} data-testid={testIds._}>
      {renderAttributeCards(attributeRules)}
    </div>
  );
}

AttributeRuleBrowser.displayName = 'AttributeRuleBrowser';

AttributeRuleBrowser.propTypes = {
  selectedNamespace: PropTypes.string,
};

AttributeRuleBrowser.defaultProps = {
  selectedNamespace: '',
};

export default React.memo(AttributeRuleBrowser);
