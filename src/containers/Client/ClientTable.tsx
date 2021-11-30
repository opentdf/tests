import { FC, useMemo } from "react";
import { Table, Button } from "antd";
import { EntityAttribute } from "../../types/entitlements";

type Props = {
  onDeleteKey: (id: string) => void;
  entityAttributes: EntityAttribute[];
};

const ClientTable: FC<Props> = (props) => {
  const { onDeleteKey, entityAttributes } = props;

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
    />
  );
};

export default ClientTable;
