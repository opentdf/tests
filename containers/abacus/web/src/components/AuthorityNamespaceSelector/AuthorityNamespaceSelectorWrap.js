import React from 'react';
import generateTestIds from '@/helpers/generateTestIds';
import PropTypes from 'prop-types';

import styles from './AuthorityNamespaceSelector.module.css';

export const testIds = generateTestIds('authority_namespace_selector', ['selector']);

const AuthorityNamespaceSelectorWrap = ({ children }) => (
  <div className={styles.container} data-testid={testIds._}>
    <div className={styles.label}>Authority Namespace</div>
    <div className={styles.component} data-testid={testIds.selector}>
      {children}
    </div>
  </div>
);

AuthorityNamespaceSelectorWrap.propTypes = {
  children: PropTypes.node.isRequired,
};

export default AuthorityNamespaceSelectorWrap;
