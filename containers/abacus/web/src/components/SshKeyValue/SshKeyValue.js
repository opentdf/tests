import { Info, Copy } from '@/icons';
import React from 'react';
import PropTypes from 'prop-types';
import { generateTestIds } from '@/helpers';
import { CopyToClipboard } from 'react-copy-to-clipboard';
import styles from './SshKeyValue.module.css';

export const testIds = generateTestIds('ssh_key_value', ['infoIcon', 'keyValue']);

function SshKeyValue({ sshKey, isCopyToMode }) {
  return (
    <CopyToClipboard text={sshKey}>
      <div className={styles.key} data-testid={testIds._}>
        <div
          className={`${styles.value} ${isCopyToMode ? styles.copyToMode : ''}`}
          data-testid={testIds.keyValue}
        >
          {sshKey}
        </div>
        {!isCopyToMode && <Info className={styles.icon} data-testid={testIds.infoIcon} />}
        {isCopyToMode && <Copy className={styles.icon} data-testid={testIds.infoIcon} />}
      </div>
    </CopyToClipboard>
  );
}

SshKeyValue.propTypes = {
  sshKey: PropTypes.string.isRequired,
  isCopyToMode: PropTypes.bool,
};

SshKeyValue.defaultProps = {
  isCopyToMode: false,
};

export default SshKeyValue;
