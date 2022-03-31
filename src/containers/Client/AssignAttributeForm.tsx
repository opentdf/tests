import { Button, Form } from "antd";
import { FC, useCallback, useEffect, useMemo, useState } from "react";
import { AttributesFiltersStore } from "../../store";
import { useUpdateEntitlement } from "./hooks/useEntitlement";
import { useDefinitionAttributes } from "../../hooks";
import { AutoComplete } from "../../components";
import { Method } from "../../types/enums";
import { toast } from "react-toastify";

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
  const { entityId, onAssignAttribute } = props;

  const [form] = useForm();
  const authorities = AttributesFiltersStore.useState(s => s.possibleAuthorities);
  const authority = AttributesFiltersStore.useState(s => s.authority);
  const { attrs, getAttrs, loading } = useDefinitionAttributes(authority);
  const [updateEntitlement] = useUpdateEntitlement();

  const [selectedName, setSelectedName] = useState();
  const [attributeValOptions, setAttributeValOptions] = useState<Option[]>();

  const authoritiesOptions = useMemo(
    () =>
      authorities.map((authority) => ({
        label: authority,
        value: authority,
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
    async (values: FormValues) => {
      const data = `${values.authority}/attr/${values.name}/value/${values.value}`;

      await updateEntitlement({
        method: Method.POST,
        path: `/entitlements/${entityId}`,
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
          options={authoritiesOptions}
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
        <Button
          htmlType="submit"
          id="assign-submit"
          loading={loading}
          type="primary"
        >
          Submit
        </Button>
      </Item>
    </Form>
  );
};

export default AssignAttributeForm;
