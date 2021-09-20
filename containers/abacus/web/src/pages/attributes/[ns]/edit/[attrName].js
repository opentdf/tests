import React from 'react';
import { useRouter } from 'next/router';
import Page from '@/components/Page';
import AttributeRuleEditCard from '@/components/AttributeRuleEditCard';

export default function AttributeValuesPage() {
  const router = useRouter();
  const { ns, attrName } = router.query;

  return (
    <Page
      contentType={Page.CONTENT_TYPES.EDIT}
      contentTitle="Edit rule"
      actionAlignment={Page.ACTION_ALIGNMENTS.LEFT}
      title="Attribute"
      description="Information attached to data and entities that controls which entities can access which data."
    >
      <Page.Breadcrumb text="Attributes" href="/attributes" />
      <Page.Breadcrumb
        text={attrName}
        // NOTE(PLAT-875): Deleted for demo
        // href={`/attributes/${encodeURIComponent(ns)}/attr/${attrName}`}
      />
      <Page.Breadcrumb text="Attribute rule" />
      <AttributeRuleEditCard ns={ns} attr={attrName} />
    </Page>
  );
}
