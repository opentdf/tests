import React from 'react';
import PropTypes from 'prop-types';
import styles from './styles/linkbutton.module.css';

const LinkButton = ({ onClick, text }) => (
  <button type="button" onClick={onClick} className={styles.button}>
    {text}
  </button>
);

LinkButton.propTypes = {
  onClick: PropTypes.func,
  text: PropTypes.string,
};

LinkButton.defaultProps = {
  onClick: () => {},
  text: '',
};

export default LinkButton;
