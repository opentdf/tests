import { FC, memo, useState, useMemo, Fragment } from "react";
import { Card, Form, Input, Button, Typography, Select } from "antd";
import { MinusCircleOutlined, PlusCircleOutlined } from "@ant-design/icons";
import { toast } from "react-toastify";

import { ATTRIBUTE_RULE_TYPES } from "../../constants/attributeRules";
import { useLazyFetch } from "../../hooks/useFetch";
import { Attribute } from "../../types/attributes";
import { entityClient } from "../../service";
import { Method } from "../../types/enums";

const { Item, List } = Form;

type Props = {
  authorityNamespace: string;
  onAddAttr: (attr: Attribute) => void;
  onAddNamespace: (namespace: string) => void;
};

type CreateAttributeValues = Omit<Attribute, "authorityNamespace">;
type CreateAuthorityValues = {
  request_authority_namespace: string;
};

const CreateAttribute: FC<Props> = (props) => {
  const { authorityNamespace, onAddAttr, onAddNamespace } = props;

  const [createAuthority] = useLazyFetch(entityClient);
  const [createAttributes] = useLazyFetch(entityClient);

  const stateOptions = useMemo(
    () => ATTRIBUTE_RULE_TYPES.map(([value, label]) => ({ value, label })),
    [],
  );

  const handleCreateAuthority = (values: CreateAuthorityValues) => {
    createAuthority<string[]>({
      method: Method.POST,
      path: `/attributes/v1/authorityNamespace`,
      params: {
        params: {
          request_authority_namespace: values.request_authority_namespace,
        },
      },
    })
      .then((response) => {
        const [lastItem] = response.data.slice(-1);
        toast.success("Authority was created");
        onAddNamespace(lastItem);
      })
      .catch(() => {
        toast.error("Authority was not created");
      });
  };

  const handleCreateAttribute = (values: CreateAttributeValues) => {
    createAttributes<Attribute>({
      method: Method.POST,
      path: `/attributes/v1/attr`,
      data: { ...values, authorityNamespace },
    })
      .then((response) => {
        onAddAttr(response.data);
        toast.success(`Attribute created for ${authorityNamespace}`);
      })
      .catch(() => {
        toast.error(`Attribute was no created for ${authorityNamespace}`);
      });
  };

  return (
    <>
      <Card title={<Typography.Title level={2}>New</Typography.Title>}>
        <Card.Grid>
          <Typography.Title level={3}>Authority</Typography.Title>

          <Form onFinish={handleCreateAuthority}>
            <Item
              name="request_authority_namespace"
              label="Create Namespace"
              rules={[{ required: true }]}
            >
              <Input />
            </Item>

            <Item>
              <Button type="primary" htmlType="submit">
                Submit
              </Button>
            </Item>
          </Form>
        </Card.Grid>

        <Card.Grid>
          <Typography.Title level={3}>
            Attribute for
            <Typography.Text italic> {authorityNamespace}</Typography.Text>
          </Typography.Title>

          <Form
            onFinish={handleCreateAttribute}
            initialValues={{ order: [undefined] }}
          >
            <Item name="name" label="Name" rules={[{ required: true }]}>
              <Input />
            </Item>

            <Item name="rule" label="Rule" rules={[{ required: true }]}>
              <Select options={stateOptions} />
            </Item>

            <Item
              name="state"
              label="State"
              rules={[{ required: true }]}
              initialValue="published"
              hidden
            >
              <Input />
            </Item>

            <List name="order">
              {(fields, { add, remove }) => {
                const lastIndex = fields.length - 1;

                return fields.map((field, index) => {
                  const isLast = lastIndex === index;

                  return (
                    <Item required label="Order" key={field.key}>
                      <Item {...field} noStyle>
                        <Input style={{ width: "calc(100% - 32px)" }} />
                      </Item>

                      <Item noStyle>
                        {isLast ? (
                          <Button
                            //! Had to use like this because https://github.com/ant-design/ant-design/issues/24698
                            onClick={() => add()}
                            icon={<PlusCircleOutlined />}
                          />
                        ) : (
                          <Button
                            onClick={() => remove(field.name)}
                            icon={<MinusCircleOutlined />}
                          />
                        )}
                      </Item>
                    </Item>
                  );
                });
              }}
            </List>

            <Item>
              <Button type="primary" htmlType="submit">
                Submit
              </Button>
            </Item>
          </Form>
        </Card.Grid>
      </Card>
    </>
  );
};

export default memo(CreateAttribute);
