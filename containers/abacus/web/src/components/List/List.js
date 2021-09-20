import React, { Children } from 'react';
import PropTypes from 'prop-types';
import { expandChildren } from '@/helpers';
import { RuleAccessType } from '@/helpers/attributeRuleTypes';
import Item from './Item';

import styles from './List.module.css';

function List({ children, isOrdered, showMode }) {
  const [, { Item: ItemChildren }] = expandChildren(children, [Item]);
  if (isOrdered) {
    return (
      <ol className={[styles.list, styles.orderedList].join(' ')} data-testid="vds-list-ordered">
        {Children.map(ItemChildren, (child) => {
          return React.cloneElement(child, { ...child.props, isOrdered: true });
        })}
      </ol>
    );
  }
  return (
    <ul
      className={`${styles.list} ${showMode ? styles.scrollSupport : ''} ${
        showMode === RuleAccessType.HIERARCHICAL ? styles.hierarchyMode : ''
      }`}
      data-testid="vds-list-unordered"
    >
      {ItemChildren}
    </ul>
  );
}

List.displayName = 'List';

List.Item = Item;

List.propTypes = {
  children: PropTypes.node,
  isOrdered: PropTypes.bool,
  showMode: PropTypes.oneOf(Object.values(RuleAccessType)),
};

List.defaultProps = {
  children: null,
  isOrdered: false,
  showMode: RuleAccessType.RESTRICTIVE,
};

export default List;
