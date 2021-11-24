import { useRouter } from 'next/router';
import { useEffect, useMemo, useState } from 'react';
import { Table } from 'antd';
import Page from '@/components/Page';
import generateTestIds from '@/helpers/generateTestIds';
import generateClient, {
  generateKeycloakAuthHeaders,
  SERVICE_ENTITLEMENT,
} from '@/helpers/requestClient';

const useClientAttributesTable = (rawData) => {
  const columns = useMemo(
    () => [
      {
        dataIndex: 'attribute',
        key: 'attribute',
        title: 'Attribute',
      },
      {
        dataIndex: 'entityId',
        key: 'entityId',
        title: 'EntityId',
      },
      {
        dataIndex: 'state',
        key: 'state',
        title: 'State',
      },
    ],
    []
  );

  const dataSource = rawData.map((item, index) => ({
    key: index,
    attribute: item.attribute,
    entityId: item.entityId,
    state: item.state,
  }));

  return { columns, dataSource };
};
const client = generateClient(SERVICE_ENTITLEMENT);

export const testIds = generateTestIds('attributes-page', ['selector']);

export default function AttributesPage() {
  const router = useRouter();
  const { ns, attrName, attrValue } = router.query;
  const attrDescription = {
    attributeUrl: `${ns}/attr/${attrName}/value/${attrValue}`,
  };
  // entitlements
  const [entitlements, setEntitlements] = useState([]);
  useEffect(() => {
    async function fetchData() {
      client.interceptors.request.use((config) => {
        // eslint-disable-next-line no-param-reassign
        config.headers = {
          ...config.headers,
          ...generateKeycloakAuthHeaders(),
        };
        return config;
      });
      const result =
        await client.get_attribute_entity_relationship_v1_attribute__attributeURI__entity__get({
          attributeURI: `${ns}/v1/attr/${attrName}/value/${attrValue}`,
        });
      setEntitlements(result.data);
    }
    fetchData();
  }, [attrName, attrValue, ns]);

  const { dataSource, columns } = useClientAttributesTable(entitlements);

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      attributeValues={attrDescription}
      actionAlignment={Page.ACTION_ALIGNMENTS.LEFT}
      title="Attribute"
      contentTitle="Entities"
      titleActions={[]}
      description="Information attached to data and entities that controls which entities can access which data."
    >
      <Page.Breadcrumb text="Attributes" href="/attributes" />
      <Page.Breadcrumb text={attrName} />
      <Page.Breadcrumb text={attrValue} />
      <div>
        {entitlements && (
          <>
            <Table dataSource={dataSource} columns={columns} pagination={false} bordered />
          </>
        )}
      </div>
    </Page>
  );
}
