import { FC, useCallback, useMemo } from "react";
import { Table } from "antd";

type Record = { clientId: string; id: string; enabled: boolean };

type Props = {
  data: Record[];
  loading: boolean;
  onRowClick: (id: string) => void;
};

const ClientsTable: FC<Props> = (props) => {
  const { data, onRowClick, loading } = props;

  const columns = useMemo(
    () => [
      { title: "Client id", key: "clientId", dataIndex: "clientId" },
      { title: "ID", key: "id", dataIndex: "id" },
      {
        title: "enabled",
        key: "enabled",
        dataIndex: "enabled",
        render: (value: Boolean) => value.toString(),
      },
    ],
    [],
  );

  const onRow = useCallback(
    (record: Record) => ({
      onClick: () => onRowClick(record.id),
    }),
    [onRowClick],
  );

  const title = useCallback(() => <b>Clients table</b>, []);
  const rowKey = useCallback((record: Record) => record.id, []);

  return (
    <Table
      data-test-id="clients-table"
      bordered
      className="table"
      columns={columns}
      dataSource={data}
      loading={loading}
      onRow={onRow}
      pagination={false}
      rowKey={rowKey}
      title={title}
    />
  );
};

export default ClientsTable;
