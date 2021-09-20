import React from 'react';
import PropTypes from 'prop-types';
import { DownArrow, UpArrow } from '@/icons';

import { RuleAccessType } from '@/helpers/attributeRuleTypes';
import styles from './List.module.css';

function renderActions(actions) {
  if (!Array.isArray(actions)) {
    return null;
  }
  return actions.map(({ key, children }) => (
    <div
      key={key}
      className={styles.action}
      data-testid="vds-list_item-detail-detail-actions-action"
    >
      {children}
    </div>
  ));
}

function Item({
  children,
  detail,
  actions,
  order,
  editable,
  orderClick,
  orderChangeMode,
  itemIndex,
  lastIndex,
  selected,
  deleted,
}) {
  const itemClasses = [styles.itemContainer];
  let innerPrepend = null;
  let outterPrepend = null;
  const isHierarchyMode = orderChangeMode === RuleAccessType.HIERARCHICAL;
  if (order) {
    itemClasses.push(styles.orderedItem);
    outterPrepend = <div className={styles.orderedDecorator} />;
    if (editable) {
      innerPrepend = <div key className={styles.orderControl} />;
    }
  } else {
    itemClasses.push(styles.unorderedItem);
    if (orderChangeMode) {
      itemClasses.push(styles.sandBoxSupport);
    }

    outterPrepend = <div key="unordered-decorator" className={styles.unorderedDecorator} />;
  }
  if (selected) {
    itemClasses.push(styles.selected);
  }
  if (deleted) {
    itemClasses.push(styles.deleted, 'deleted-item');
  }
  return (
    <li className={itemClasses.join(' ')} data-testid="vds-list_item">
      {isHierarchyMode ? (
        <div className={styles.indexTitleBlock}>
          <span className={styles.indexTitle}>{`0${itemIndex + 1}.`}</span>
        </div>
      ) : (
        outterPrepend
      )}
      <div className={`${styles.itemInnerContainer} ${orderChangeMode ? styles.orderList : ''}`}>
        {orderClick && isHierarchyMode && (
          <div className={styles.arrowsContainer} data-testid="vds-arrowsContainer">
            {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events,jsx-a11y/no-static-element-interactions */}
            <div className={styles.arrowBlock} onClick={() => orderClick('up')}>
              {itemIndex !== 0 && <UpArrow data-testid="vds-UpArrow" />}
            </div>
            {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events,jsx-a11y/no-static-element-interactions */}
            <div className={styles.arrowBlock} onClick={() => orderClick('down')}>
              {lastIndex !== itemIndex && <DownArrow data-testid="vds-downArrow" />}
            </div>
          </div>
        )}
        {innerPrepend}
        <div
          className={`${styles.itemContent} ${orderChangeMode ? styles.paddingItemView : ''}`}
          data-testid="vds-list_item-content"
        >
          {children}
          <div className={styles.itemDetail} data-testid="vds-list_item-detail">
            <div className={styles.itemDetailTitle} data-testid="vds-list_item-detail-content">
              {detail}
            </div>
            <div className={styles.itemDetailAction} data-testid="vds-list_item-detail-actions">
              {renderActions(actions)}
            </div>
          </div>
        </div>
      </div>
    </li>
  );
}

Item.displayName = 'Item';

Item.propTypes = {
  children: PropTypes.node.isRequired,
  detail: PropTypes.node,
  actions: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      children: PropTypes.node,
    })
  ),
  editable: PropTypes.bool,
  order: PropTypes.number,
  orderClick: PropTypes.func,
  itemIndex: PropTypes.number,
  lastIndex: PropTypes.number,
  orderChangeMode: PropTypes.string,
  selected: PropTypes.bool,
  deleted: PropTypes.bool,
};

Item.defaultProps = {
  detail: null,
  actions: null,
  editable: false,
  selected: false,
  deleted: false,
  order: null,
  orderChangeMode: '',
  orderClick: null,
  itemIndex: 0,
  lastIndex: 0,
};

export default Item;
