import { Button, Cascader, Popover, Typography } from "antd";
import FilterForm from "./FilterForm";

enum ORDER {
  ASC = "ASC",
  DES = "DES",
}

const ORDER_MAP = new Map([
  [ORDER.ASC, "-"],
  [ORDER.DES, "+"],
]);

const SORT_OPTIONS = ["id", "entity_id", "namespace", "name", "value"];

const CASCADER_OPTIONS = [
  {
    children: SORT_OPTIONS.map((value) => ({ value, label: value })),
    label: ORDER.ASC,
    value: ORDER_MAP.get(ORDER.ASC) || "",
  },
  {
    children: SORT_OPTIONS.map((value) => ({ value, label: value })),
    label: ORDER.DES,
    value: ORDER_MAP.get(ORDER.DES) || "",
  },
];

const AttributesHeader = () => {
  const onChange = (value: any) => {
    console.log(`value`, value);
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flex: "1 0 auto",
      }}
    >
      <Typography.Title level={2}>Attribute Rules</Typography.Title>

      <div
        style={{
          flexBasis: "50%",
          justifyContent: "flex-end",
          display: "flex",
        }}
      >
        <Cascader
          multiple
          onChange={onChange}
          options={CASCADER_OPTIONS}
          placeholder="Sort by..."
        />

        <Popover
          content={<FilterForm />}
          placement="bottomRight"
          trigger="click"
        >
          <Button>Filters</Button>
        </Popover>
      </div>
    </div>
  );
};

export default AttributesHeader;
