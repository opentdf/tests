import React from 'react';
import PropTypes from 'prop-types';

const TBody = ({ children, className }) => <tbody className={className}>{children}</tbody>;

TBody.propTypes = {
  children: PropTypes.node,
  className: PropTypes.string,
};

TBody.defaultProps = {
  children: undefined,
  className: '',
};

export default TBody;
