import React from 'react';
import Page from '@/components/Page';
import Redirect from '@/components/Redirect';

function AttributeNamePage() {
  return (
    <Page>
      <Redirect href="/attributes" />
    </Page>
  );
}

export default AttributeNamePage;
