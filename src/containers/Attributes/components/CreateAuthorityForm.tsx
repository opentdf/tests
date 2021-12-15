import { FC, memo } from "react";
import { Typography, Form, Input, Button } from "antd";
import {AuthorityDefinition} from "../../../types/attributes";

const { Item } = Form;
const { Title } = Typography;

type Props = { onFinish: (values: AuthorityDefinition) => void };

const CreateAuthorityForm: FC<Props> = (props) => {
  return (
    <>
      <Title level={3}>Authority</Title>

      <Form onFinish={props.onFinish}>
        <Item
          name="authority"
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
