import PropTypes from 'prop-types';
import clsx from 'clsx';

import styles from './styles/TH.module.css';

const TH = ({ className, children, onClick, min, width, align }) => {
  const thClassNames = clsx(styles.headerCell, className, {
    [styles.min]: min,
  });

  return (
    <th className={thClassNames} onClick={onClick} style={{ width, textAlign: align }}>
      {children}
    </th>
  );
};

TH.propTypes = {
  className: PropTypes.string,
  align: PropTypes.string,
  onClick: PropTypes.func,
  children: PropTypes.node,
  min: PropTypes.bool,
  width: PropTypes.string,
};

TH.defaultProps = {
  className: '',
  align: 'left',
  onClick: () => {},
  children: null,
  min: false,
  width: null,
};

export default TH;
