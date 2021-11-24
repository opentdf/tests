import PropTypes from 'prop-types';
import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import List from '@/components/List';
import { RuleAccessType } from '@/helpers/attributeRuleTypes';
import styles from './AttributeListCard.module.css';

const generateAction = (ns, attrName, attrValue) => [
  {
    key: 'entities-detail',
    children: (
      <Link
        shallow
        href={`/attributes/${encodeURIComponent(ns)}/attr/${attrName}/value/${attrValue}`}
      >
        {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
        <a>Entities &amp; details</a>
      </Link>
    ),
  },
];

const AttributeList = ({
  namespace,
  attributeName,
  ruleType,
  attributeObject,
  attributeRule,
  orderList,
  onOrderChange,
}) => {
  const [localOrder, setOrder] = useState([...orderList]);

  useEffect(() => {
    setOrder(orderList);
  }, [orderList]);

  const updateOrder = useCallback(
    (index, moveTo) => {
      if ((!index && moveTo === 'up') || (index === localOrder.length - 1 && moveTo === 'down')) {
        return;
      }

      const moveToIndex = moveTo === 'up' ? index - 1 : index + 1;
      const toUpdate = [...localOrder];
      [toUpdate[moveToIndex], toUpdate[index]] = [toUpdate[index], toUpdate[moveToIndex]];

      setOrder(toUpdate);
      onOrderChange(
        toUpdate,
        { ...attributeObject, order: [...toUpdate] },
        {
          [attributeRule.authorityNamespace]: { ...attributeRule, order: [...toUpdate] },
        }
      );
    },
    [localOrder, onOrderChange, attributeObject, attributeRule]
  );

  return (
    <div>
      <div className={styles.attributeList}>Current attribute values</div>
      <div
        className={`${styles.main} ${
          ruleType === RuleAccessType.HIERARCHICAL ? styles.hierarchyMode : ''
        }`}
      >
        {localOrder && localOrder.length ? (
          <List showMode={ruleType}>
            {localOrder.map((value, i) => {
              return (
                <List.Item
                  key={value}
                  detail={namespace}
                  actions={generateAction(namespace, attributeName, value)}
                  orderChangeMode={ruleType}
                  orderClick={(moveTo) => updateOrder(i, moveTo)}
                  itemIndex={i}
                  lastIndex={localOrder.length - 1}
                >
                  {value}
                </List.Item>
              );
            })}
          </List>
        ) : (
          <div className={`${styles.emptyListBlock} ${styles.whiteBlock}`}>
            <span>This attribute name doesn’t have any values yet.</span>
          </div>
        )}
      </div>
    </div>
  );
};

const AttrObjectType = PropTypes.shape({
  authorityNamespace: PropTypes.string,
  name: PropTypes.string,
  order: PropTypes.arrayOf(PropTypes.string),
  rule: PropTypes.string,
  state: PropTypes.string,
});
AttributeList.propTypes = {
  ruleType: PropTypes.string,
  namespace: PropTypes.string,
  attributeName: PropTypes.string,
  attributeObject: AttrObjectType,
  attributeRule: AttrObjectType,
  orderList: PropTypes.arrayOf(PropTypes.string),
  onOrderChange: PropTypes.func,
};

AttributeList.defaultProps = {
  ruleType: '',
  namespace: '',
  attributeName: '',
  attributeObject: {},
  attributeRule: {},
  orderList: [],
  onOrderChange: () => {},
};

export default AttributeList;
