import { Button, Form } from "antd";
import { FC, useCallback, useEffect, useMemo, useState } from "react";
import { useAuthorities } from "../../hooks";
import { useUpdateEntitlement } from "./hooks/useEntitlement";
import { useAttrs } from "../../hooks/useAttributes";
import { AutoComplete } from "../../components";
import { Method } from "../../types/enums";
import { toast } from "react-toastify";

const { Item, useForm } = Form;

type Option = { label: string; value: string };
type Props = { entityId: string };
type FormValues = {
  authority: string;
  name: string;
  value: string;
};

const AssignAttributeForm: FC<Props> = (props) => {
  const [form] = useForm();
  const [authority] = useAuthorities();
  const { attrs } = useAttrs(authority);
  const [updateEntitlement] = useUpdateEntitlement();

  const [selectedName, setSelectedName] = useState();
  const [attributeValOptions, setAttributeValOptions] = useState<Option[]>();

  useEffect(() => {
    form.setFieldsValue({
      authority,
    });
  }, [authority, form]);

  const nameOptions = useMemo(
    () =>
      attrs.map((attribute) => ({
        label: attribute.name,
        value: attribute.name,
      })),
    [attrs],
  );

  useEffect(() => {
    const selectedAttr = attrs.find(
      (attribute) => attribute.name === selectedName,
    );

    const options = selectedAttr?.order.map((option) => ({
      label: option,
      value: option,
    }));

    setAttributeValOptions(options);
  }, [attrs, selectedName]);

  const onAttributeName = useCallback((selectedVal) => {
    setSelectedName(selectedVal);
  }, []);

  const onFinish = useCallback(
    (values: FormValues) => {
      const params = `${values.authority}/attr/${values.name}/value/${values.value}`;

      updateEntitlement({
        method: Method.PUT,
        path: `/entitlement/v1/entity/${props.entityId}/attribute`,
        params: [params],
      }).then((res) => {
        console.log(`res`, res);
        toast.success("Updated");
      });
    },
    [props.entityId, updateEntitlement],
  );

  return (
    <Form form={form} layout="inline" size="middle" onFinish={onFinish}>
      <Item label="Authority Namespace">
        <AutoComplete
          defaultActiveFirstOption
          disabled
          name="authority"
          placeholder="Authority..."
          style={{ width: 200 }}
        />
      </Item>

      <Item label="Attribute Name" name="name">
        <AutoComplete
          name="name"
          onSelect={onAttributeName}
          options={nameOptions}
          placeholder="input here"
          style={{ width: 200 }}
        />
      </Item>

      <Item label="Attribute Value" name="value">
        <AutoComplete
          name="value"
          options={attributeValOptions}
          placeholder="input here"
          style={{ width: 200 }}
        />
      </Item>
      <Item>
        <Button type="primary" htmlType="submit">
          Submit
        </Button>
      </Item>
    </Form>
  );
};

export default AssignAttributeForm;
