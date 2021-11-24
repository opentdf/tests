import PropTypes from 'prop-types';
import clsx from 'clsx';

import styles from './styles/TR.module.css';

const TR = ({ className, children, onClick, id, disabled, isBordered, newEntity }) => {
  const classNames = clsx(styles.dataRow, className, {
    [styles.disabled]: disabled,
    [styles.bordered]: isBordered,
    [styles.clickable]: onClick,
    [styles.newEntity]: newEntity,
  });

  return (
    <tr className={classNames} onClick={onClick} tabIndex={onClick ? '0' : undefined} data-id={id}>
      {children}
    </tr>
  );
};

TR.propTypes = {
  className: PropTypes.string,
  children: PropTypes.node,
  onClick: PropTypes.func,
  id: PropTypes.string,
  isBordered: PropTypes.bool,
  disabled: PropTypes.bool,
  newEntity: PropTypes.bool,
};

TR.defaultProps = {
  className: '',
  children: null,
  onClick: () => {},
  id: '',
  isBordered: false,
  disabled: false,
  newEntity: false,
};

export default TR;
