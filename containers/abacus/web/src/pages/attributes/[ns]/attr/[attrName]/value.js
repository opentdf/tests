import React from 'react';
import Page from '@/components/Page';
import Redirect from '@/components/Redirect';
import useRoutePath from '@/hooks/useRoutePath';

function AttributeValuePage() {
  const routePath = useRoutePath();

  return (
    <Page>
      <Redirect href={routePath.paths.attribute.attr} />
    </Page>
  );
}

export default AttributeValuePage;
