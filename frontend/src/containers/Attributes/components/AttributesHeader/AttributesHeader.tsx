import styles from "./AttributesHeader.module.css";
import { Button, Cascader, Popover, Typography, Pagination, Select } from "antd";

import FilterForm from "../FilterForm";
import { AttributesFiltersStore } from "../../../../store";

const { Option } = Select;

enum ORDER {
  ASC = "ASC",
  DES = "DES",
}

const ORDER_MAP = new Map([
  [ORDER.ASC, ''],
  [ORDER.DES, '-'],
]);

const SORT_OPTIONS = ['name', 'id', 'rule', 'values'];

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


type AttributesHeaderProps = {
  total: number;
}

const AttributesHeader = ({ total }: AttributesHeaderProps) => {
  const onChange = (value: any): void => {
    const sort = value.join('');
    AttributesFiltersStore.update(s => {
      s.query.sort = sort;
    });
  };

  const currentPageNumber = AttributesFiltersStore.useState(s => s.pageNumber);

  const handlePaginationChange = (pageNumber: number): void => {
    if (pageNumber > currentPageNumber) {
      AttributesFiltersStore.update(s => {
        s.query.offset += 1;
        s.pageNumber += 1;
      });
    } else {
      AttributesFiltersStore.update(s => {
        s.query.offset -= 1;
        s.pageNumber -= 1;
      });
    }
  };

  const authorities = AttributesFiltersStore.useState(s => s.possibleAuthorities);
  const authority = AttributesFiltersStore.useState(s => s.authority);

  return (
    <div className={styles.attributeHeader}>
      <Typography.Title level={2}>
        Attribute Rules
      </Typography.Title>

      <div className={styles.cascaderContainer}>
        <Select
          value={authority}
          placeholder="Loading Authorities"
          onChange={(value) => {
            AttributesFiltersStore.update(s => {
              s.authority = value
            })
          }}
        >
          {authorities.map(val => <Option key={String(val)} value={String(val)}>{val}</Option>)}
        </Select>
        <Pagination
          onChange={handlePaginationChange}
          total={total}
          pageSize={10}
          current={currentPageNumber}
          showTotal={(total) => `Total ${total} items`}
        />

        <Cascader
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
