import PropTypes from 'prop-types';
import clsx from 'clsx';

import styles from './styles/TD.module.css';

const TD = ({ children, className, align, ...rest }) => (
  <td style={{ textAlign: align }} className={clsx(className, styles.dataCell)} {...rest}>
    {children}
  </td>
);

TD.propTypes = {
  className: PropTypes.string,
  align: PropTypes.string,
  children: PropTypes.node,
};

TD.defaultProps = {
  className: '',
  align: 'left',
  children: null,
};

export default TD;
