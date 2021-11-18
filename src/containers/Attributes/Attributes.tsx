import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Form, List, Radio, Table, Typography } from "antd";

import { components } from "../../attributes";
import { useAuthorities, useAttrs } from "../../hooks";
import CreateAttribute from "./CreateAttribute";
import { useLazyFetch } from "../../hooks/useFetch";
import { entityClient } from "../../service";
import { Method } from "../../types/enums";

import "./Attributes.css";
import { OrderCard } from "../../components";
import { EntityAttribute } from "../../types/entitlements";
import { OrderList } from "./components";

type Attribute = components["schemas"]["Attribute"];
type AttributeRuleType = components["schemas"]["AttributeRuleType"];
const tuple = <T extends AttributeRuleType[]>(...args: T) => args;
const attributeRuleTypes = tuple("hierarchy", "anyOf", "allOf");
// @ts-ignore

const TABLE_COLUMNS = [
  {
    title: "Attribute",
    dataIndex: "attribute",
    key: "attribute",
  },
  {
    title: "EntityId",
    dataIndex: "entityId",
    key: "entityId",
  },
  {
    title: "State",
    dataIndex: "state",
    key: "state",
  },
];

const Attributes = () => {
  const authorities = useAuthorities();
  const [getAttrEntities, entities] =
    useLazyFetch<EntityAttribute[]>(entityClient);

  const [authority] = authorities;
  const { attrs } = useAttrs(authority);
  const [form] = Form.useForm();

  const [activeAuthority, setActiveAuthority] = useState(authority);
  const [activeTabKey, setActiveTab] = useState("");
  const [isEdit, setIsEdit] = useState(false);
  const [activeOrderList, setActiveOrderList] = useState<string[]>([]);

  const handleAuthorityChange = (e: any) => {
    setActiveAuthority(e.target.value);
  };

  const handleEditClick = () => {
    setIsEdit(true);
  };

  const handleOrderClick = useCallback(
    (attribute: Attribute, orderItem: string) => {
      const { authorityNamespace, name } = attribute;

      const path = encodeURIComponent(
        `${authorityNamespace}/attr/${name}/value/${orderItem}`,
      );

      getAttrEntities({
        method: Method.GET,
        path: `/entitlement/v1/attribute/${path}/entity/`,
      });

      setActiveTab(orderItem);
      setActiveOrderList(attribute.order);
    },
    [getAttrEntities],
  );

  useEffect(() => {
    form.setFieldsValue({ authorities: authority });
  }, [authority, form]);

  const handleReorder = useCallback((list) => {
    setActiveOrderList(list);
  }, []);

  return (
    <>
      <Typography.Title level={2}>Attribute Rules</Typography.Title>

      <List
        grid={{ gutter: 3, xs: 1, column: 2 }}
        footer={<CreateAttribute authorityNameSpace={activeAuthority} />}
        header={
          <Form form={form}>
            <Form.Item name="authorities">
              <Radio.Group
                buttonStyle="solid"
                defaultValue={activeAuthority}
                onChange={handleAuthorityChange}
                options={authorities}
                optionType="button"
                value={activeAuthority}
              />
            </Form.Item>
          </Form>
        }
      >
        {attrs.map((attr) => {
          const { name, order, state } = attr;

          const handleTabChange = (tab: string) => {
            handleOrderClick(attr, tab);
          };

          const isActive = order.find(
            (orderItem) => orderItem === activeTabKey,
          );

          const tabList = order.map((orderItem) => ({
            key: orderItem,
            tab: orderItem,
          }));

          return (
            <List.Item key={attr.name}>
              <OrderCard
                activeTabKey={activeTabKey}
                name={name}
                onEditClick={handleEditClick}
                onTabChange={handleTabChange}
                state={state}
                tabList={tabList}
              >
                {isActive && (
                  <Table columns={TABLE_COLUMNS} dataSource={entities} />
                )}

                {isActive && isEdit && (
                  <div>
                    <OrderList
                      list={activeOrderList}
                      onReorder={handleReorder}
                    />
                  </div>
                )}
              </OrderCard>
            </List.Item>
          );
        })}
      </List>
    </>
  );
};

export default Attributes;
