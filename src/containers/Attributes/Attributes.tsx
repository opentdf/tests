import { useCallback, useEffect, useState } from "react";
import { Card, Typography, List, Form, Radio } from "antd";

import { components } from "../../attributes";
import { useAuthorities, useAttrs } from "../../hooks";
import { Link } from "react-router-dom";
import CreateAttribute from "./CreateAttribute";
import { useLazyFetch } from "../../hooks/useFetch";
import { entityClient } from "../../service";
import { Method } from "../../types/enums";

type Attribute = components["schemas"]["Attribute"];
type AttributeRuleType = components["schemas"]["AttributeRuleType"];
const tuple = <T extends AttributeRuleType[]>(...args: T) => args;
const attributeRuleTypes = tuple("hierarchy", "anyOf", "allOf");
// @ts-ignore

const Attributes = () => {
  const authorities = useAuthorities();
  const [getAttrEntities, data] = useLazyFetch(entityClient);

  console.log(`data`, data);
  const [authority] = authorities;
  const { attrs } = useAttrs(authority);
  const [form] = Form.useForm();

  const [activeAuthority, setActiveAuthority] = useState(authority);

  const handleAuthorityChange = (e: any) => {
    setActiveAuthority(e.target.value);
  };

  const handleOrderClick = useCallback(
    (attribute: Attribute, orderItem: string) => {
      const { authorityNamespace, name } = attribute;

      const path = `${authorityNamespace}/attr/${name}/value/${orderItem}`;

      getAttrEntities({
        method: Method.GET,
        path: `/entitlement/v1/attribute/${path}/entity`,
      });
    },
    [getAttrEntities],
  );

  useEffect(() => {
    form.setFieldsValue({ authorities: authority });
  }, [authority, form]);

  const renderItem = useCallback(
    (item: Attribute) => {
      const { name, authorityNamespace, order, state } = item;

      return (
        <List.Item>
          <Card
            title={
              <div>
                <Typography.Title level={3}>{name}</Typography.Title>
                <Typography.Text strong>{state}</Typography.Text>
                <Typography.Text type="secondary"> Access</Typography.Text>
              </div>
            }
            actions={[
              <Link to={""} key="details">
                Details
              </Link>,
              <Link to={""} key="edit">
                Edit Rule
              </Link>,
            ]}
          >
            {order.map((orderItem) => (
              <div onClick={() => handleOrderClick(item, orderItem)}>
                <Card.Grid
                  key={orderItem}
                  style={{
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: "column",
                  }}
                >
                  <Typography.Text strong>{orderItem} </Typography.Text>
                  <Typography.Text type="secondary">
                    {authorityNamespace}
                  </Typography.Text>
                </Card.Grid>
              </div>
            ))}
          </Card>
        </List.Item>
      );
    },
    [handleOrderClick],
  );

  return (
    <>
      <Typography.Title level={2}>Attribute Rules</Typography.Title>

      <List
        grid={{ gutter: 16, column: 2 }}
        dataSource={attrs}
        renderItem={renderItem}
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
      />
    </>
  );
};

export default Attributes;
