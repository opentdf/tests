import { FC, useMemo } from "react";
import { Table, Button } from "antd";

type TableData = { attribute: string; entityId: string };

type Props = {
  data?: TableData[];
  loading: boolean;
  onDeleteKey: (row: TableData) => void;
};

const ClientTable: FC<Props> = (props) => {
  const { onDeleteKey, data, loading } = props;

  const columns = useMemo(
    () => [
      {
        dataIndex: "attribute",
        key: "attribute",
        title: "Attribute",
      },
      {
        dataIndex: "entityId",
        key: "entityId",
        title: "EntityId",
      },
      {
        title: "Action",
        dataIndex: "",
        key: "x",
        render: (row: TableData) => (
          <Button type="link" onClick={() => onDeleteKey(row)}>
            Delete
          </Button>
        ),
      },
    ],
    [onDeleteKey],
  );

  return (
    <Table
      bordered
      className="table"
      columns={columns}
      dataSource={data}
      pagination={false}
      loading={loading}
    />
  );
};

export default ClientTable;
