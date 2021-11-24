import { Button } from 'antd';
import { useMemo } from 'react';

const useClientAttributesTable = (rawData, onDeleteKey) => {
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
      {
        title: 'Action',
        dataIndex: '',
        key: 'x',
        render: (row) => (
          <Button type="link" onClick={() => onDeleteKey(row)}>
            Delete
          </Button>
        ),
      },
    ],
    [onDeleteKey]
  );

  const dataSource = rawData.map((item, index) => ({
    key: index,
    attribute: item.attribute,
    entityId: item.entityId,
    state: item.state,
  }));

  return { columns, dataSource };
};

export default useClientAttributesTable;
