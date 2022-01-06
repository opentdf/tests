import { Button, Form } from "antd";
import { FC, useCallback, useEffect, useMemo, useState } from "react";
import { useAuthorities } from "../../hooks";
import { useUpdateEntitlement } from "./hooks/useEntitlement";
import { useAttributesDefinitions } from "../../hooks";
import { AutoComplete } from "../../components";
import { Method } from "../../types/enums";
import { toast } from "react-toastify";

// @ts-ignore
const serverData = window.SERVER_DATA;
const { Item, useForm } = Form;

type Option = { label: string; value: string };
type Props = {
  entityId: string;
  onAssignAttribute: () => void;
};
type FormValues = {
  authority: string;
  name: string;
  value: string;
};

const AssignAttributeForm: FC<Props> = (props) => {
  const { onAssignAttribute, entityId } = props;

  const [form] = useForm();
  const authorities = useAuthorities();
  const [authority] = authorities;
  const { attrs, getAttrs, loading } = useAttributesDefinitions(authority);
  const [updateEntitlement] = useUpdateEntitlement();

  const [selectedName, setSelectedName] = useState();
  const [attributeValOptions, setAttributeValOptions] = useState<Option[]>();

  const authoritiesOptions = useMemo(
    () =>
      authorities.map((attribute) => ({
        label: attribute,
        value: attribute,
      })),
    [authorities],
  );

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

    const options = selectedAttr?.order.map((option: string) => ({
      label: option,
      value: option,
    }));

    setAttributeValOptions(options);
  }, [attrs, selectedName]);

  const onAttributeName = useCallback((selectedVal) => {
    setSelectedName(selectedVal);
  }, []);

  const onFinish = useCallback(
    async (values: FormValues) => {
      const data = `${values.authority}/attr/${values.name}/value/${values.value}`;

      await updateEntitlement({
        method: Method.POST,
        path: serverData.entitlements + `/entitlements/${entityId}`,
        data: [data],
      })
        .then(() => {
          toast.success("Entitlement updated!");
          onAssignAttribute();
        })

        .catch(() => {
          toast.error("Could not update entitlement");
        });
    },
    [entityId, onAssignAttribute, updateEntitlement],
  );

  const handleAuthorityChange = async (namespace: string) => {
    await getAttrs(namespace);
  };

  return (
    <Form form={form} layout="inline" size="middle" onFinish={onFinish}>
      <Item label="Authority Namespace">
        <AutoComplete
          defaultActiveFirstOption
          name="authority"
          onSelect={handleAuthorityChange}
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
        <Button type="primary" htmlType="submit" loading={loading}>
          Submit
        </Button>
      </Item>
    </Form>
  );
};

export default AssignAttributeForm;
