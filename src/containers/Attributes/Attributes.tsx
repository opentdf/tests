import { useCallback, useEffect, useMemo, useState } from "react";
import { List, Typography, Select, Cascader } from "antd";

import { useAuthorities, useAttrs } from "../../hooks";

import CreateAttribute from "./CreateAttribute";
import { AttributesHeader, AttributeListItem } from "./components";

import "./Attributes.css";
// @ts-ignore

const { Option } = Select;

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
    value: ORDER_MAP.get(ORDER.ASC),
  },
  {
    children: SORT_OPTIONS.map((value) => ({ value, label: value })),
    label: ORDER.DES,
    value: ORDER_MAP.get(ORDER.DES),
  },
];

const Attributes = () => {
  const authorities = useAuthorities();
  const [authority] = authorities;

  const [stateAuthorities, setStateAuthorities] = useState(authorities);
  const [activeAuthority, setActiveAuthority] = useState(authority);
  const { attrs, getAttrs } = useAttrs(activeAuthority);
  const [stateAttrs, setStateAttrs] = useState(attrs);
  const [sort, setSort] = useState({
    order: ORDER_MAP.get(ORDER.ASC),
    value: "",
  });

  useEffect(() => {
    setStateAttrs(attrs);
  }, [attrs]);

  useEffect(() => {
    setStateAuthorities(authorities);
  }, [authorities]);

  const handleAuthorityChange = useCallback((value: string) => {
    setActiveAuthority(value);
  }, []);

  const onAddAttr = useCallback((attr) => {
    setStateAttrs((prevState) => [...prevState, attr]);
  }, []);

  const onAddNamespace = useCallback(
    (namespace) => {
      setStateAuthorities((prevState) => [...prevState, namespace]);
      getAttrs(namespace);
    },
    [getAttrs],
  );

  const footer = useMemo(
    () => (
      <CreateAttribute
        authorityNamespace={activeAuthority}
        onAddAttr={onAddAttr}
        onAddNamespace={onAddNamespace}
      />
    ),
    [activeAuthority, onAddAttr, onAddNamespace],
  );

  const header = useMemo(
    () => (
      <AttributesHeader
        activeAuthority={activeAuthority}
        authorities={stateAuthorities}
        authority={authority}
        onAuthorityChange={handleAuthorityChange}
      />
    ),
    [activeAuthority, stateAuthorities, authority, handleAuthorityChange],
  );

  return (
    <>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flex: "1 0 auto",
        }}
      >
        <Typography.Title level={2}>Attribute Rules</Typography.Title>

        <div style={{ flexBasis: "50%" }}>
          <Cascader
            changeOnSelect
            options={CASCADER_OPTIONS}
            placeholder="Sort by..."
          />
        </div>
      </div>

      <List
        grid={{ gutter: 3, xs: 2, column: 2 }}
        footer={footer}
        header={header}
      >
        {stateAttrs.map((attr) => (
          <AttributeListItem
            activeAuthority={activeAuthority}
            attr={attr}
            key={attr.name}
          />
        ))}
      </List>
    </>
  );
};

export default Attributes;
