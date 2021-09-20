import React from 'react';
// NOTE(PLAT-875): Deleted for demo
// import { Button } from '@/components/Virtruoso';
import Page from '@/components/Page';
import generateTestIds from '@/helpers/generateTestIds';
import EntitiesTable from '@/components/EntitiesTable';

export const testIds = generateTestIds('attributes-page', ['selector']);

export default function AttributesPage() {
  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      // NOTE(PLAT-875): Deleted for demo
      // actions={[
      //   {
      //     key: 'new-entity',
      //     children: (
      //       <Button variant={Button.VARIANT.PRIMARY} size={Button.SIZE.MEDIUM}>
      //         New Entity
      //       </Button>
      //     ),
      //   },
      // ]}
      actionAlignment={Page.ACTION_ALIGNMENTS.RIGHT}
      title="Entity"
      description="A person, organization, device, or process who will access data based on their attributes."
    >
      <Page.Breadcrumb text="Entities" />
      <EntitiesTable isViewEntityMode />
    </Page>
  );
}
