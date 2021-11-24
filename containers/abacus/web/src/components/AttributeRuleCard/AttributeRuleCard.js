import PropTypes from 'prop-types';
import Link from 'next/link';

import Card from '@/components/Card';
import List from '@/components/List';
import { generateTestIds } from '@/helpers';

import styles from './AttributeRuleCard.module.css';

export const testIds = generateTestIds('attribute_rule_card', [
  'attributeTitleHeader',
  'attributeDetailHeader',
  'newValueAction',
  'editRuleAction',
]);

export function formatAccessType(accessType) {
  switch (accessType) {
    case 'hierarchy':
      return 'Hierarchical';
    case 'allOf':
      return 'Restrictive';
    case 'anyOf':
      return 'Permissive';
    default:
      return accessType;
  }
}

const generateAction = (ns, attrName, attrValue) => [
  {
    key: 'entities-detail',
    children: (
      <Link
        shallow
        href={`/attributes/${encodeURIComponent(ns)}/attr/${attrName}/value/${attrValue}`}
      >
        {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
        <a>Entities &amp; details</a>
      </Link>
    ),
  },
];

function AttributeRuleCard({
  name,
  // NOTE(PLAT-875): Deleted for demo
  // eslint-disable-next-line no-unused-vars
  focused,
  accessType,
  values,
  authorityNamespace,
  // NOTE(PLAT-875): Deleted for demo
  // eslint-disable-next-line no-unused-vars
  onNewValueAction,
  // NOTE(PLAT-875): Deleted for demo
  // eslint-disable-next-line no-unused-vars
  onEditRuleAction,
}) {
  const accessTypeNode = (
    <span>
      <strong className={styles.cardAccessType}>{formatAccessType(accessType)}</strong>
      <span className={styles.cardAccessValue}>Access</span>
    </span>
  );

  return (
    <div className={styles.card} data-testid={testIds._}>
      <div className={styles.listWrapper}>
        <Card.Header
          id="attribute-title"
          title={name}
          actions={[
            // {
            //   key: 'new-value',
            //   children: (
            //     <a
            //       href="javascript;"
            //       onClick={onNewValueAction}
            //       data-testid={testIds.newValueAction}
            //     >
            //       + New Value
            //     </a>
            //   ),
            // },
            ...(focused
              ? []
              : [
                  {
                    key: 'details',
                    children: (
                      <Link
                        shallow
                        href={`/attributes/${encodeURIComponent(authorityNamespace)}/attr/${name}`}
                      >
                        <a>Details</a>
                      </Link>
                    ),
                  },
                ]),
          ]}
          data-testid={testIds.attributeTitleHeader}
        />
        <div
          className={styles.subhead}
          id="attribute-detail"
          data-testid={testIds.attributeTitleHeader}
        >
          <span>{accessTypeNode}</span>
          <Link shallow href={`/attributes/${encodeURIComponent(authorityNamespace)}/edit/${name}`}>
            {/* eslint-disable-next-line jsx-a11y/click-events-have-key-events,jsx-a11y/no-static-element-interactions */}
            <span
              data-testid={testIds.editRuleAction}
              onClick={onEditRuleAction}
              className={styles.menuLink}
            >
              Edit Rule
            </span>
          </Link>
        </div>
        <List>
          {values.map((value) => {
            return (
              <List.Item
                key={value}
                detail={authorityNamespace}
                actions={generateAction(authorityNamespace, name, value)}
              >
                {value}
              </List.Item>
            );
          })}
        </List>
      </div>
    </div>
  );
}

AttributeRuleCard.displayName = 'AttributeRuleCard';

AttributeRuleCard.propTypes = {
  name: PropTypes.string.isRequired,
  authorityNamespace: PropTypes.string.isRequired,
  values: PropTypes.arrayOf(PropTypes.string),
  accessType: PropTypes.string.isRequired,
  focused: PropTypes.bool,
  onNewValueAction: PropTypes.func,
  onEditRuleAction: PropTypes.func,
};

AttributeRuleCard.defaultProps = {
  values: [],
  focused: false,
  onNewValueAction: () => {},
  onEditRuleAction: () => {},
};

export default AttributeRuleCard;
