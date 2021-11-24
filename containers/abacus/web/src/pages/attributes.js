/* eslint-disable no-param-reassign */
import { useState, useContext } from 'react';
import { Form, Input, Button, message } from 'antd';
import 'antd/dist/antd.css';
import Page from '@/components/Page';
import AuthorityNamespaceSelector from '@/components/AuthorityNamespaceSelector';
import generateTestIds from '@/helpers/generateTestIds';
import AttributeRuleBrowser from '@/components/AttributeRuleBrowser';
import useAuthorityNamespaces from '@/hooks/useAuthorityNamespaces';
import { AttributeCreateContext } from '@/hooks/useAttributeRuleCreate';
import { AuthorityNamespacesCreateContext } from '@/hooks/useAuthorityNamespacesCreate';

export const testIds = generateTestIds('attributes-page', ['selector']);

export default function AttributesPage() {
  const authorityNamespaces = useAuthorityNamespaces();
  const [selectedNamespace, setSelectedNamespace] = useState('');
  const { setAttributeRule } = useContext(AttributeCreateContext);
  const { setNamespace } = useContext(AuthorityNamespacesCreateContext);

  const onFinishAttribute = async (formInfo) => {
    formInfo.authorityNamespace = selectedNamespace || `Namespace didn't load`;
    formInfo.order = formInfo.order.split(/[ ,]+/);
    message.success('Attribute rule loaded successfully');
    setAttributeRule(formInfo);
  };

  const onFinishFailedAttribute = () => {
    message.error('Invalid form inputs');
  };

  const onFinishNamespace = async (namespace) => {
    setNamespace(namespace);
    message.success('Namespace loaded successfully');
  };

  const onFinishFailedNamespace = () => {
    message.error('Invalid form inputs');
  };

  return (
    <Page
      contentType={Page.CONTENT_TYPES.VIEW}
      actionAlignment={Page.ACTION_ALIGNMENTS.RIGHT}
      title="Attribute"
      description="Information attached to data and entities that controls which entities can access which data."
    >
      <Page.Breadcrumb text="Attributes" />
      <AuthorityNamespaceSelector
        selectedNamespace={selectedNamespace}
        setSelectedNamespace={setSelectedNamespace}
        authorityNamespaces={authorityNamespaces}
      />
      <div id="createNamespaceFormContainer" style={{ marginBottom: '20px' }}>
        <Form
          name="createNamespace"
          labelCol={{ span: 8 }}
          wrapperCol={{ span: 16 }}
          initialValues={{ remember: true }}
          onFinish={onFinishNamespace}
          onFinishFailed={onFinishFailedNamespace}
          autoComplete="off"
          style={{
            border: '1px solid #021E4A',
            borderRadius: '9px',
            width: '500px',
            margin: 'auto',
            padding: '0px 50px 0px 50px',
          }}
        >
          <h3 style={{ margin: '10px' }}>Create Namespace:</h3>
          <Form.Item
            label="Namespace"
            name="request_authority_namespace"
            rules={[{ required: true, message: 'Please input a Namespace to create' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item wrapperCol={{ offset: 8, span: 16 }}>
            <Button type="primary" htmlType="submit">
              Create
            </Button>
          </Form.Item>
        </Form>
      </div>

      <div id="createAttributeFormContainer" style={{ marginBottom: '20px' }}>
        <Form
          name="createAttribute"
          labelCol={{ span: 8 }}
          wrapperCol={{ span: 16 }}
          initialValues={{ remember: true }}
          onFinish={onFinishAttribute}
          onFinishFailed={onFinishFailedAttribute}
          autoComplete="off"
          style={{
            border: '1px solid #021E4A',
            borderRadius: '9px',
            width: '500px',
            margin: 'auto',
            padding: '0px 50px 0px 50px',
          }}
        >
          <h3 style={{ margin: '10px' }}>Create Attribute:</h3>
          <Form.Item
            label="Name"
            name="name"
            rules={[{ required: true, message: 'Name is required' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            label="Rule"
            name="rule"
            rules={[{ required: true, message: 'Rule is required' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            label="State"
            name="state"
            rules={[{ required: true, message: 'State is required' }]}
          >
            <Input />
          </Form.Item>

          <Form.Item
            label="Order"
            name="order"
            rules={[
              {
                required: true,
                message:
                  'Please type your Attribute values separated by space or comma in the desired hierarchical order',
              },
            ]}
          >
            <Input />
          </Form.Item>

          <Form.Item wrapperCol={{ offset: 8, span: 16 }}>
            <Button type="primary" htmlType="submit">
              Create
            </Button>
          </Form.Item>
        </Form>
      </div>

      <AttributeRuleBrowser selectedNamespace={selectedNamespace} />
    </Page>
  );
}
