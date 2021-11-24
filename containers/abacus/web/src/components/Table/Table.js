import PropTypes from 'prop-types';
import clsx from 'clsx';

import styles from './styles/Table.module.css';

const Table = ({ children, className, isScrollableBody }) => (
  <table
    className={clsx(className, styles.table, {
      [styles.scrollableBody]: isScrollableBody,
    })}
  >
    {children}
  </table>
);

Table.propTypes = {
  children: PropTypes.node,
  className: PropTypes.string,
  isScrollableBody: PropTypes.bool,
};

Table.defaultProps = {
  children: null,
  className: '',
  isScrollableBody: false,
};

export default Table;
