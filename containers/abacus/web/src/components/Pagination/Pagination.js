import React from 'react';
import PropTypes from 'prop-types';
import clsx from 'clsx';
import { generateTestIds } from '@/helpers';
import styles from './styles/Pagination.module.css';

export const testIds = generateTestIds('attribute_rule_card', ['clickNext', 'clickBack']);

const Pagination = ({ from, to, of, onBackClick, onNextClick }) => (
  <span className={styles.wrapper}>
    <span className={styles.index}>
      {/* eslint-disable-next-line react/jsx-one-expression-per-line */}
      {from} - {to} of {of}
    </span>
    <span className={styles.buttons}>
      <button
        type="button"
        className={styles.button}
        onClick={onBackClick}
        data-testid={testIds.clickBack}
      >
        <span className={clsx(styles.arrow, styles.left)} />
      </button>
      <button
        type="button"
        className={styles.button}
        onClick={onNextClick}
        data-testid={testIds.clickNext}
      >
        <span className={clsx(styles.arrow, styles.right)} />
      </button>
    </span>
  </span>
);
//
Pagination.propTypes = {
  from: PropTypes.string,
  of: PropTypes.string,
  to: PropTypes.string,
  onBackClick: PropTypes.func,
  onNextClick: PropTypes.func,
};

Pagination.defaultProps = {
  from: '',
  of: '',
  to: '',
  onBackClick: () => {},
  onNextClick: () => {},
};

export default Pagination;
