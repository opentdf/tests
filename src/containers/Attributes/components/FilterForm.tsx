import { Button, Col, Form, Input, Row } from "antd";
import { AttributesFiltersStore } from '../../../store';

const { Item } = Form;

const FilterForm = () => {
  return (
    <Form
      name="filter"
      labelCol={{ span: 24 }}
      wrapperCol={{ span: 24 }}
      onFinish={(values) => {
        AttributesFiltersStore.update(store => {
          store.query = { ...values };
        })
      }}
      autoComplete="off"
      layout="vertical"
    >
      <Row gutter={[8, 8]}>
        <Col>
          <Item label="Rule" name="rule">
            <Input />
          </Item>
        </Col>
        <Col>
          <Item label="Name" name="name">
            <Input />
          </Item>
        </Col>
      </Row>

      <Row gutter={[8, 8]}>
        <Col>
          <Item label="Order" name="order">
            <Input />
          </Item>
        </Col>
      </Row>

      <Row gutter={[8, 8]}>
        <Col offset={12} span={6}>
          <Item>
            <Button block type="primary" htmlType="submit">
              Submit
            </Button>
          </Item>
        </Col>
        <Col span={6}>
          <Item>
            <Button block type="primary" htmlType="reset">
              Clear
            </Button>
          </Item>
        </Col>
      </Row>
    </Form>
  );
};

export default FilterForm;
