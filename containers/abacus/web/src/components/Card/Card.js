import React from 'react';
import PropTypes from 'prop-types';
import { expandChildren } from '@/helpers';
import generateTestIds from '@/helpers/generateTestIds';
import CardHeader from './CardHeader';

import styles from './styles/card.module.css';

export const testIds = generateTestIds('card');

function Card({ children, ...props }) {
  const [nextChildren, { CardHeader: cardHeaderChildren = [] }] = expandChildren(children, [
    CardHeader,
  ]);

  return (
    <div {...props} className={styles.card} data-testid="vds-card">
      {cardHeaderChildren.map((element, i) =>
        React.cloneElement(
          element,
          { key: element.props.id, ...element.props, isSubHeader: !!i },
          element.children
        )
      )}
      <div className={styles.content} data-testid="vds-card-content">
        {nextChildren}
      </div>
    </div>
  );
}

Card.displayName = 'Card';

Card.propTypes = {
  children: PropTypes.node,
};

Card.defaultProps = {
  children: null,
};

export default Card;
