import { Button, Cascader, Popover, Typography, Pagination } from "antd";
import FilterForm from "../FilterForm";

import styles from "./AttributesHeader.module.css";

enum ORDER {
  ASC = "ASC",
  DES = "DES",
}

const ORDER_MAP = new Map([
  [ORDER.ASC, "-"],
  [ORDER.DES, "+"],
]);

const SORT_OPTIONS = ["entity_id", "name", "namespace", "value"];

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

  const handlePaginationChange = (pageNumber: number) => {
    console.log(`pageNumber`, pageNumber);
  };

  return (
    <div className={styles.attributeHeader}>
      <Typography.Title level={2}>Attribute Rules</Typography.Title>

      <div className={styles.cascaderContainer}>
        <Pagination
          onChange={handlePaginationChange}
          total={50}
          showTotal={(total) => `Total ${total} items`}
        />

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
