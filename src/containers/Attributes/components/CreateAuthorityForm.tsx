import { FC, memo } from "react";
import { Typography, Form, Input, Button } from "antd";

const { Item } = Form;
const { Title } = Typography;

type CreateAuthorityValues = {
  request_authority_namespace: string;
};

type Props = { onFinish: (values: CreateAuthorityValues) => void };

const CreateAuthorityForm: FC<Props> = (props) => {
  return (
    <>
      <Title level={3}>Authority</Title>

      <Form onFinish={props.onFinish}>
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
    </>
  );
};

export default memo(CreateAuthorityForm);
