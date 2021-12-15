import { FC, useMemo } from "react";
import { Table, Button } from "antd";
import { Entitlements } from "../../types/entitlements";

type Props = {
  entityAttributes?: Entitlements;
  loading: boolean;
  onDeleteKey: (id: { [key: string]: string[] }) => void;
};

const ClientTable: FC<Props> = (props) => {
  const { onDeleteKey, entityAttributes, loading } = props;

    // @ts-ignore
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
        dataIndex: "state",
        key: "state",
        title: "State",
      },
      {
        title: "Action",
        dataIndex: "",
        key: "x",
        render: (row: { [key: string]: string[] }) => (
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
      // dataSource={entityAttributes}
      pagination={false}
      loading={loading}
    />
  );
};

export default ClientTable;
