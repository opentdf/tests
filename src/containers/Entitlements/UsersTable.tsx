import { FC, useCallback, useMemo } from "react";
import { Table } from "antd";

type Record = { username: string; id: string; enabled: boolean };

type Props = {
  loading: boolean;
  onRowClick: (id: string) => void;
  data: Record[];
};

const UsersTable: FC<Props> = (props) => {
  const { data, onRowClick, loading } = props;

  const columns = useMemo(
    () => [
      { title: "Username", key: "username", dataIndex: "username" },
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

  const title = useCallback(() => <b>Users table</b>, []);
  const rowKey = useCallback((record: Record) => record.id, []);

  return (
    <Table
      data-test-id="users-table"
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

export default UsersTable;
