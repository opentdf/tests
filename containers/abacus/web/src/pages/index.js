import Link from 'next/link';
import Page from '@/components/Page';

export default function Home() {
  return (
    <Page>
      <Page.Breadcrumb text="Home" />

      <div id="attributeDescription" style={{ margin: '20px 0px 20px 0px' }}>
        <Link href="/attributes">
          <a style={{ textDecoration: 'none', color: 'inherit' }}>
            <h3>Attributes</h3>
            <span>
              TDF protocol supports ABAC (Attribute Based Access Control). This allows TDF protocol
              to implement policy driven and highly scalable access control mechanism.
            </span>
          </a>
        </Link>
      </div>

      <div id="entityDescription" style={{ margin: '20px 0px 20px 0px' }}>
        <Link href="/entities">
          <a style={{ textDecoration: 'none', color: 'inherit' }}>
            <h3>Entities</h3>
            <span>
              Entities can consist of non-person entities representing a process or server, or
              person entities representing a user. Entities can be assigned multiple Attributes to
              implement fine grained access permissions to TDF files.
            </span>
          </a>
        </Link>
      </div>
    </Page>
  );
}
