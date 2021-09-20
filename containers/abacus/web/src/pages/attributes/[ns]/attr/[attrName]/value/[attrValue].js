import React from 'react';
import { useRouter } from 'next/router';
import { Button } from '@/components/Virtruoso';
import Page from '@/components/Page';
import generateTestIds from '@/helpers/generateTestIds';

import EntitiesTable from '@/components/EntitiesTable';
import useRoutePath from '@/hooks/useRoutePath';
import useAttributeRule from '@/hooks/useAttributeRule';

export const testIds = generateTestIds('attributes-page', ['selector']);

export default function AttributesPage() {
  const router = useRouter();
  const routePath = useRoutePath();
  const { ns, attrName, attrValue } = router.query;
  const attributeRule = useAttributeRule(attrName, attrValue, ns);
  const attrDescription = {
    attributeUrl: `${ns}/v1/attr/${attrName}/value/${attrValue}`,
    keyAccessUrl: attributeRule.kasUrl,
    publicKey: attributeRule.pubKey,
  };
  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      // NOTE(PLAT-875): Deleted for demo
      // actions={[
      //   {
      //     key: 'edit',
      //     children: (
      //       <Button variant={Button.VARIANT.SECONDARY} size={Button.SIZE.MEDIUM}>
      //         Edit
      //       </Button>
      //     ),
      //   },
      //   {
      //     key: 'delete',
      //     children: (
      //       <Button variant={Button.VARIANT.NO_OUTLINE} size={Button.SIZE.MEDIUM}>
      //         Delete
      //       </Button>
      //     ),
      //   },
      // ]}
      attributeValues={attrDescription}
      actionAlignment={Page.ACTION_ALIGNMENTS.LEFT}
      title="Attribute"
      contentTitle={`Entities with “${attributeRule.displayName}”`}
      titleActions={[
        {
          key: 'assign',
          children: (
            <Button
              variant={Button.VARIANT.PRIMARY}
              size={Button.SIZE.SMALL}
              onClick={() => routePath.pushAttributeValue('add-entity')}
            >
              Assign Entity
            </Button>
          ),
        },
      ]}
      description="Information attached to data and entities that controls which entities can access which data."
    >
      <Page.Breadcrumb text="Attributes" href="/attributes" />
      <Page.Breadcrumb
        text={attrName}
        // NOTE(PLAT-875): Deleted for demo
        // href={`/attributes/${encodeURIComponent(ns)}/attr/${attrName}`}
      />
      <Page.Breadcrumb text={attrValue} />
      <EntitiesTable attrName={attrName} attrValue={attrValue} namespace={ns} />
    </Page>
  );
}
