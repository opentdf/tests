import { Form, Radio, RadioChangeEvent } from "antd";
import { FC, memo, useEffect } from "react";

const { useForm, Item } = Form;

type Props = {
  onAuthorityChange: (authority: string) => void;
  authority: string;
  activeAuthority: string;
  authorities: string[];
};

const AttributesListHeader: FC<Props> = (props) => {
  const { activeAuthority, authorities, authority, onAuthorityChange } = props;

  const [form] = useForm();

  useEffect(() => {
    form.setFieldsValue({ authorities: authority });
    onAuthorityChange(authority);
  }, [authority, form, onAuthorityChange]);

  const handleOnChange = (e: RadioChangeEvent) => {
    onAuthorityChange(e.target.value);
  };

  return (
    <Form
      form={form}
      initialValues={{
        authorities: authority,
      }}
    >
      <Item name="authorities">
        <Radio.Group
          buttonStyle="solid"
          onChange={handleOnChange}
          options={authorities}
          optionType="button"
          value={activeAuthority}
        />
      </Item>
    </Form>
  );
};

export default memo(AttributesListHeader);
