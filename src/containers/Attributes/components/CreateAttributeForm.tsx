import { FC, useMemo } from "react";
import { Button, Form, Input, Select, Typography } from "antd";
import { PlusCircleOutlined, MinusCircleOutlined } from "@ant-design/icons";

import { ATTRIBUTE_RULE_TYPES } from "../../../constants/attributeRules";
import { Attribute } from "../../../types/attributes";

const { Item, List } = Form;

type CreateAttributeValues = Omit<Attribute, "authorityNamespace">;

type Props = {
  authorityNamespace: string;
  onFinish: (values: CreateAttributeValues) => void;
};

const CreateAttributeForm: FC<Props> = (props) => {
  const { onFinish, authorityNamespace } = props;

  const stateOptions = useMemo(
    () => ATTRIBUTE_RULE_TYPES.map(([value, label]) => ({ value, label })),
    [],
  );

  return (
    <>
      <Typography.Title level={3}>
        Attribute for
        <Typography.Text italic> {authorityNamespace}</Typography.Text>
      </Typography.Title>

      <Form onFinish={onFinish} initialValues={{ order: [undefined] }}>
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
    </>
  );
};

export default CreateAttributeForm;
