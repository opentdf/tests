import PropTypes from 'prop-types';
import clsx from 'clsx';

import styles from './styles/cardHeader.module.css';

function renderActions(actions) {
  return actions.map(({ key, children }) => (
    <div key={key} style={styles.action} data-testid="vds-card_header-actions-action">
      {children}
    </div>
  ));
}

function CardHeader({ title, actions, isSubHeader }) {
  return (
    <div
      className={clsx(styles.header, !!isSubHeader && styles.subheader)}
      data-testid="vds-card_header"
    >
      <div className={styles.title} data-testid="vds-card_header-title">
        {title}
      </div>
      <div className={styles.actions} data-testid="vds-card_header-actions">
        {renderActions(actions)}
      </div>
    </div>
  );
}

CardHeader.displayName = 'CardHeader';

CardHeader.propTypes = {
  title: PropTypes.node.isRequired,
  actions: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      children: PropTypes.node.isRequired,
    })
  ),
  isSubHeader: PropTypes.bool,
};

CardHeader.defaultProps = {
  actions: [],
  isSubHeader: false,
};

export default CardHeader;
