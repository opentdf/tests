import { useEffect, useState } from 'react';
import PropTypes from 'prop-types';
import { Select } from '@/components/Virtruoso';
import generateTestIds from '@/helpers/generateTestIds';

import { RuleAccessType, RuleAccessTypeDescription } from '@/helpers/attributeRuleTypes';
import styles from './AttributeRuleSelector.module.css';

export const testIds = generateTestIds('authority_namespace_selector', ['selector']);

function AttributeRuleSelector({ ruleType, onTypeChange }) {
  const [options] = useState([
    { label: 'Hierarchical Access', value: RuleAccessType.HIERARCHICAL },
    { label: 'Permissive Access', value: RuleAccessType.PERMISSIVE },
    { label: 'Restrictive Access', value: RuleAccessType.RESTRICTIVE },
  ]);
  const [selectedValue, setSelectedValue] = useState({ label: '', value: '' });
  const valueChange = (data) => {
    setSelectedValue({ ...data });
    onTypeChange(data.value);
  };

  useEffect(() => {
    setSelectedValue({ ...options.find((item) => item.value === ruleType) });
  }, [options, ruleType]);

  return (
    <div className={styles.container} data-testid={testIds._}>
      <div className={styles.label}>Attribute rule</div>
      <div className={styles.wrapSelector}>
        <div className={styles.component} data-testid={testIds.selector}>
          <Select
            isLoading={!selectedValue.value}
            value={selectedValue}
            options={options}
            onChange={valueChange}
            isDisabled={!selectedValue.value}
          />
        </div>
        <div className={styles.titleBlock}>{RuleAccessTypeDescription[ruleType]()}</div>
      </div>
    </div>
  );
}

AttributeRuleSelector.propTypes = {
  ruleType: PropTypes.string.isRequired,
  onTypeChange: PropTypes.func.isRequired,
};

export default AttributeRuleSelector;
