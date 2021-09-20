import React from 'react';
import PropTypes from 'prop-types';
// NOTE(PLAT-875): Deleted for demo
// import Link from 'next/link';
import Card from '@/components/Card';
import List from '@/components/List';
import getAttributeUri from '@/helpers/getAttributeUri';

import styles from './EntityCard.module.css';

const generateAction = (action, description) => [
  {
    key: 'entities-detail',
    children: (
      // eslint-disable-next-line jsx-a11y/click-events-have-key-events,jsx-a11y/no-static-element-interactions
      <a style={{ cursor: 'pointer' }} onClick={action}>
        {description}
      </a>
    ),
  },
];

function EntityCard({
  name,
  values,
  authorityNamespace,
  selectedValue,
  deleteEntity,
  assignEntity,
  deletedList,
}) {
  return (
    <div className={styles.card}>
      <Card.Header
        id="attribute-title"
        title={name}
        // actions={[
        //   {
        //     key: 'details',
        //     children: (
        //       <Link
        //         shallow
        //         href={`/attributes/${encodeURIComponent(authorityNamespace)}/attr/${name}`}
        //       >
        //         <a>Details</a>
        //       </Link>
        //     ),
        //   },
        // ]}
      />
      <List>
        {values
          .sort((a, b) => a.localeCompare(b))
          .map((value) => {
            const params = {
              ns: authorityNamespace,
              attr: name,
              val: value,
            };
            const isDeleted = deletedList.has(
              getAttributeUri({ ns: authorityNamespace, attr: name, val: value })
            );
            const isSelected =
              getAttributeUri({ ns: authorityNamespace, attr: name, val: value }) === selectedValue;

            const action = isDeleted ? () => assignEntity(params) : () => deleteEntity(params);
            const description = isDeleted ? 'Restore' : 'Remove from entity';

            return (
              <List.Item
                selected={isSelected}
                deleted={isDeleted}
                key={value}
                detail={authorityNamespace}
                actions={generateAction(action, description)}
              >
                {value}
              </List.Item>
            );
          })}
      </List>
    </div>
  );
}

EntityCard.displayName = 'EntityCard';

EntityCard.propTypes = {
  deleteEntity: PropTypes.func,
  assignEntity: PropTypes.func,
  name: PropTypes.string.isRequired,
  authorityNamespace: PropTypes.string.isRequired,
  values: PropTypes.arrayOf(PropTypes.string),
  deletedList: PropTypes.instanceOf(Set),
  selectedValue: PropTypes.string,
};

EntityCard.defaultProps = {
  deleteEntity: () => {},
  assignEntity: () => {},
  values: [],
  selectedValue: '',
  deletedList: new Set(),
};

export default EntityCard;
