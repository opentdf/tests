import React, { useState } from 'react';
// NOTE(PLAT-875): Deleted for demo
// import { Button } from '@/components/Virtruoso';
import Page from '@/components/Page';
import AuthorityNamespaceSelector from '@/components/AuthorityNamespaceSelector';
import generateTestIds from '@/helpers/generateTestIds';
import AttributeRuleBrowser from '@/components/AttributeRuleBrowser';
import useAuthorityNamespaces from '@/hooks/useAuthorityNamespaces';

export const testIds = generateTestIds('attributes-page', ['selector']);

export default function AttributesPage() {
  const authorityNamespaces = useAuthorityNamespaces();
  const [selectedNamespace, setSelectedNamespace] = useState('');

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      // NOTE(PLAT-875): Deleted for demo
      // actions={[
      //   {
      //     key: 'new-attribute',
      //     children: (
      //       <Button variant={Button.VARIANT.PRIMARY} size={Button.SIZE.MEDIUM}>
      //         New Attribute
      //       </Button>
      //     ),
      //   },
      // ]}
      actionAlignment={Page.ACTION_ALIGNMENTS.RIGHT}
      title="Attribute"
      description="Information attached to data and entities that controls which entities can access which data."
    >
      <Page.Breadcrumb text="Attributes" />
      <AuthorityNamespaceSelector
        selectedNamespace={selectedNamespace}
        setSelectedNamespace={setSelectedNamespace}
        authorityNamespaces={authorityNamespaces}
      />
      <AttributeRuleBrowser selectedNamespace={selectedNamespace} />
    </Page>
  );
}
