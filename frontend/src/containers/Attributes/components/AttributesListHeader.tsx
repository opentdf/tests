import { Form, Radio, RadioChangeEvent } from "antd";
import { FC, memo, useEffect } from "react";
import { AuthorityDefinition} from "../../../types/attributes";
const { useForm, Item } = Form;

type Props = {
  onAuthorityChange: (authority: AuthorityDefinition) => void;
  authority: AuthorityDefinition;
  activeAuthority: AuthorityDefinition;
  authorities: AuthorityDefinition[];
};

const AttributesHeader: FC<Props> = (props) => {
  const { activeAuthority, authorities, authority, onAuthorityChange } = props;

  const [form] = useForm();

  useEffect(() => {
    form.setFieldsValue({ authorities: authority });
    onAuthorityChange(authority);
  }, [authority, form, onAuthorityChange]);

  const handleOnChange = (e: RadioChangeEvent) => {
    const authorityDefinition: AuthorityDefinition = {'authority': e.target.value};
    onAuthorityChange(authorityDefinition);
  };

  return (
    <Form
      form={form}
      initialValues={{
        authorities: [authority],
      }}
    >
      <Item name="authorities">
        <Radio.Group
          buttonStyle="solid"
          onChange={handleOnChange}
          optionType="button"
          value={activeAuthority}
        />
      </Item>
    </Form>
  );
};

export default memo(AttributesHeader);
