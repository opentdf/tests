import React, { useContext } from 'react';
import PropTypes from 'prop-types';
import clsx from 'clsx';
import Head from 'next/head';
import Link from 'next/link';
import { Layout, Menu } from '@/components/Virtruoso';
import { expandChildren, generateTestIds } from '@/helpers';
import AttributeValueDescription from '@/components/AttributeValueDescription';
import { Loader } from '@/hooks/useLoader';
import EntityValueDescription from '@/components/EntityValueDescription/EntityValueDescription';
import Breadcrumb from './Breadcrumb';

import styles from './Page.module.css';

export const testIds = generateTestIds('page', [
  'headerBreadcrumb',
  'header',
  'headerTop',
  'content',
  'contentTitle',
  'loading',
]);

const ACTION_ALIGNMENTS = {
  LEFT: 'left',
  RIGHT: 'right',
};

const CONTENT_TYPES = {
  VIEW: 'view',
  EDIT: 'edit',
};

const renderActionList = (actionList) =>
  actionList.map((item) => (
    <div key={item.key} className={styles.action}>
      {item.children}
    </div>
  ));

function renderBreadcrumb(breadcrumb) {
  const list = [];
  React.Children.forEach(breadcrumb, (child, i) => {
    // conditional key cause prop gets from next.js router, has initial value as null
    if (i > 0) {
      list.push(<Breadcrumb separator key={`${child.text || i}-'separator'`} />);
    }
    list.push(React.cloneElement(child, { ...child.props, key: child.text || i }));
  });
  return (
    <div className={styles.pageHeaderBreadcrumb} data-testid={testIds.headerBreadcrumb}>
      <ul className={styles.breadcrumb}>{list}</ul>
    </div>
  );
}

function generateActions(actionList, alignment) {
  return (
    <div
      className={[
        clsx(styles.actions, {
          [styles.actionAlignmentRight]: alignment === ACTION_ALIGNMENTS.RIGHT,
          [styles.actionAlignmentLeft]: alignment === ACTION_ALIGNMENTS.LEFT,
        }),
      ]}
    >
      {renderActionList(actionList)}
    </div>
  );
}

function renderContentTitle(title, actionList = []) {
  return title ? (
    <div className={styles.contentTitle} data-testid={testIds.contentTitle}>
      {title}
      {renderActionList(actionList)}
    </div>
  ) : null;
}

function renderDescription(title, description) {
  let descriptionEl;
  if (description) {
    descriptionEl = (
      <>
        <span className={styles.descriptionSpacer}>&mdash;</span>
        <span className={styles.descriptionContent}>{description}</span>
      </>
    );
  }

  return (
    <div className={styles.description}>
      <span className={styles.descriptionTitle}>{title}</span>
      {descriptionEl}
    </div>
  );
}

function renderAttributeValues(attributeValues, entityValues) {
  if (attributeValues || entityValues) {
    return (
      <div className={styles.attributeDescription}>
        {/* eslint-disable-next-line react/jsx-props-no-spreading */}
        {attributeValues && <AttributeValueDescription {...attributeValues} />}
        {entityValues && (
          <EntityValueDescription
            name={entityValues.name}
            email={entityValues.email}
            userId={entityValues.userId}
          />
        )}
      </div>
    );
  }
  return null;
}

function Page({
  actions,
  actionAlignment,
  children,
  contentType,
  contentTitle,
  description,
  title,
  titleActions,
  attributeValues,
  entityValues,
}) {
  const { isLoading } = useContext(Loader);
  const [nextChildren, { Breadcrumb: breadcrumbChildren }] = expandChildren(children, [Breadcrumb]);

  let headTitle = `Abacus`;
  if (title) {
    headTitle += ` - ${title}`;
  }

  return (
    <>
      <Head>
        <title>{headTitle}</title>
        <link rel="icon" href="/favicons/favicon.ico" />
      </Head>
      <Layout>
        <Layout.Header company="Virtru" title="Abacus">
          <Menu>
            <Menu.MenuItem>
              <Link shallow href="/attributes">
                <span className={styles.menuLink}>Attributes</span>
              </Link>
            </Menu.MenuItem>
            <Menu.MenuItem>
              <Link shallow href="/entities">
                <span className={styles.menuLink}>Entities</span>
              </Link>
            </Menu.MenuItem>
          </Menu>
        </Layout.Header>
        <div className={styles.page} data-testid={testIds._}>
          {isLoading ? (
            <div className={styles.loading} data-testid={testIds.loading}>
              Loading...
            </div>
          ) : (
            <>
              <div className={styles.pageHeader} data-testid={testIds.header}>
                <div className={styles.pageHeaderTop} data-testid={testIds.headerTop}>
                  {renderBreadcrumb(breadcrumbChildren)}
                  {generateActions(actions, actionAlignment)}
                </div>
                {renderDescription(title, description)}
              </div>
              {renderAttributeValues(attributeValues, entityValues)}
              {renderContentTitle(contentTitle, titleActions)}
              <div
                className={clsx(styles.content, {
                  [styles.actionEdit]: contentType === CONTENT_TYPES.EDIT,
                  [styles.actionView]: contentType === CONTENT_TYPES.VIEW,
                })}
                data-testid={testIds.content}
              >
                {nextChildren}
              </div>
            </>
          )}
        </div>
      </Layout>
    </>
  );
}

Page.displayName = 'Page';

Page.ACTION_ALIGNMENTS = ACTION_ALIGNMENTS;

Page.CONTENT_TYPES = CONTENT_TYPES;

Page.propTypes = {
  actions: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      children: PropTypes.node,
    })
  ),
  actionAlignment: PropTypes.oneOf(Object.values(Page.ACTION_ALIGNMENTS)),
  children: PropTypes.node,
  titleActions: PropTypes.arrayOf(
    PropTypes.shape({
      key: PropTypes.string.isRequired,
      children: PropTypes.node,
    })
  ),
  contentTitle: PropTypes.string,
  contentType: PropTypes.oneOf([...Object.values(Page.CONTENT_TYPES), '']),
  description: PropTypes.string,
  title: PropTypes.string,
  attributeValues: PropTypes.shape({
    attributeUrl: PropTypes.string,
    keyAccessUrl: PropTypes.string,
    publicKey: PropTypes.string,
  }),
  entityValues: PropTypes.shape({
    name: PropTypes.string,
    email: PropTypes.string,
    userId: PropTypes.string,
  }),
};

Page.defaultProps = {
  actions: [],
  actionAlignment: Page.ACTION_ALIGNMENTS.RIGHT,
  children: null,
  contentTitle: null,
  contentType: '',
  description: null,
  title: null,
  titleActions: [],
  attributeValues: null,
  entityValues: null,
};

export default Page;
