import Page from '@/components/Page';
import Redirect from '@/components/Redirect';

function NamespacePage() {
  return (
    <Page>
      <Redirect href="/attributes" />
    </Page>
  );
}

export default NamespacePage;
