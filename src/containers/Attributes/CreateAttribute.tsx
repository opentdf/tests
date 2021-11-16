import { FC } from "react";
import { Card, Form, Input, Button, Typography } from "antd";

import { useLazyFetch } from "../../hooks/useFetch";
import { entityClient } from "../../service";
import { Method } from "../../types/enums";

const { Item } = Form;

type Props = { authorityNameSpace: string };

const CreateAttribute: FC<Props> = (props) => {
  const { authorityNameSpace } = props;

  const [createAuthority] = useLazyFetch(entityClient);
  const [createAttributes] = useLazyFetch(entityClient);

  const handleCreateAuthority = (values: {
    request_authority_namespace: string;
  }) => {
    createAuthority({
      method: Method.POST,
      path: `/attributes/v1/authorityNamespace`,
      params: values,
    });
  };

  const handleCreateAttribute = (values: {
    name: string;
    order: string;
    rule: string;
    state: string;
  }) => {
    const order = values.order.split(/[ ,]+/);

    createAttributes({
      method: Method.POST,
      path: `/attributes/v1/attr`,
      params: { ...values, order, authorityNameSpace },
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
              label="Create NameSpace"
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
            <Typography.Text italic> {authorityNameSpace}</Typography.Text>
          </Typography.Title>

          <Form onFinish={handleCreateAttribute}>
            <Item name="name" label="Name" rules={[{ required: true }]}>
              <Input />
            </Item>

            <Item name="rule" label="Rule" rules={[{ required: true }]}>
              <Input />
            </Item>

            <Item name="state" label="State" rules={[{ required: true }]}>
              <Input />
            </Item>

            <Item name="order" label="Order" rules={[{ required: true }]}>
              <Input />
            </Item>

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

export default CreateAttribute;
