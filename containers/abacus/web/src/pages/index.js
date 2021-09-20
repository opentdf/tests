import React from 'react';
import Page from '@/components/Page';
import { Button } from '@/components/Virtruoso';

export default function Home() {
  return (
    <Page
      actions={[
        {
          key: 'new-attribute',
          children: (
            <Button variant={Button.VARIANT.SECONDARY} size={Button.SIZE.MEDIUM}>
              Edit
            </Button>
          ),
        },
      ]}
      title="Abacus"
      description="Abacus home page"
      contentTitle="Home View"
    >
      <Page.Breadcrumb text="Home" />
      Content here
    </Page>
  );
}
