import useAttributeRules from '@/hooks/useAttributeRules';
import PropTypes from 'prop-types';
import React, { useCallback, useEffect, useState } from 'react';
import RuleSandbox from '@/components/RuleSandbox';
import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';
import AttributeRuleSelector from '@/components/AttributeRuleSelector';
import BottomButtons from '@/components/AttributeRuleEditCard/BottomButtons';
import AttributeList from '@/components/AttributeListCard';
import styles from './AttributeRileEditCard.module.css';

const AttributeEditCard = ({ attr, ns }) => {
  const attributeRules = useAttributeRules(ns);
  const [attributeObject, setAttribute] = useState({
    authorityNamespace: ns,
    name: attr,
    order: [],
    rule: 'hierarchy',
    state: 'active',
  });
  const [attributeRule, setAttributeRule] = useState({ order: [] });
  useEffect(() => {
    setAttributeRule(
      (_attributeRules) => attributeRules.find((item) => item.name === attr) || _attributeRules
    );
  }, [attr, attributeRules]);

  useEffect(() => {
    setAttribute({ ...attributeObject, rule: attributeRule.rule });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attributeRule]);

  const { order } = attributeRule;
  const [orderList, setOrderList] = useState([]);
  const [ruleSandboxConfig, setRuleSandboxConfig] = useState({
    [attributeRule.authorityNamespace]: { ...attributeRule },
  });
  const listOnChange = useCallback((_orderList, _attribute, _sandboxConfig) => {
    setOrderList(_orderList);
    setAttribute(_attribute);
    setRuleSandboxConfig(_sandboxConfig);
  }, []);
  const requestUpdateAttribute = useCallback(async () => {
    const client = generateClient(SERVICE_EAS);
    await client['src.web.attribute_name.update'](
      {
        name: attr,
      },
      attributeObject
    );
  }, [attr, attributeObject]);
  const updateRule = (type) => {
    setAttribute({ ...attributeObject, rule: type });
    setAttributeRule({ ...attributeRule, rule: type });
  };
  const isEmptyList = !!(orderList && orderList.length);

  useEffect(() => {
    if (order.length) {
      setOrderList([...order]);
      setAttribute((_attributeObject) => {
        setRuleSandboxConfig({
          [_attributeObject.authorityNamespace]: { ..._attributeObject, order: [...order] },
        });

        return { ..._attributeObject, order: [...order] };
      });
    }
  }, [order, attributeObject.rule]);

  return (
    <div className={styles.wrapper}>
      {attributeObject.rule && (
        <AttributeRuleSelector ruleType={attributeObject.rule} onTypeChange={updateRule} />
      )}

      <div className={styles.attributeListMain}>
        <div className={styles.container}>
          <div>
            <AttributeList
              namespace={ns}
              attributeName={attr}
              ruleType={attributeObject.rule}
              onOrderChange={listOnChange}
              orderList={orderList}
              attributeObject={attributeObject}
              attributeRule={attributeRule}
            />
          </div>
          {isEmptyList ? (
            <RuleSandbox attribute={ruleSandboxConfig} />
          ) : (
            <div className={styles.emptyListBlock} />
          )}
          <BottomButtons requestUpdateAttribute={requestUpdateAttribute} />
        </div>
      </div>
    </div>
  );
};

AttributeEditCard.propTypes = {
  attr: PropTypes.string,
  ns: PropTypes.string,
};

AttributeEditCard.defaultProps = {
  attr: '',
  ns: '',
};

export default AttributeEditCard;
