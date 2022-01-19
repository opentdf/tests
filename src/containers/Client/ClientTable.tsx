import { FC, useMemo } from "react";
import { Table, Button } from "antd";
import { EntityAttribute } from "../../types/entitlements";

type Props = {
  entityAttributes?: EntityAttribute[];
  loading: boolean;
  onDeleteKey: (id: string) => void;
};

const ClientTable: FC<Props> = (props) => {
  const { onDeleteKey, entityAttributes, loading } = props;

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
        render: (row: EntityAttribute) => (
          <Button type="link" onClick={() => onDeleteKey(row.attribute)}>
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
      dataSource={entityAttributes}
      pagination={false}
      loading={loading}
    />
  );
};

export default ClientTable;
