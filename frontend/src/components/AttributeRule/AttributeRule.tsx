import { FC, memo, useCallback, useMemo, useState } from "react";
import { Form, Select } from "antd";

import { ATTRIBUTE_RULE_TYPES } from "../../constants/attributeRules";
import { LABELS_MAP } from "./constants";

import "./AttributeRule.css";

type Props = {
  onRuleChange: (rule: string) => void;
};

const AttributeRule: FC<Props> = (props) => {
  const { onRuleChange } = props;

  const [selectedStrategy, setSelectedStrategy] = useState(() => {
    const initialValue = ATTRIBUTE_RULE_TYPES[0][0];
    onRuleChange(initialValue);
    return initialValue;
  });

  const options = useMemo(
    () => ATTRIBUTE_RULE_TYPES.map(([value, label]) => ({ value, label })),
    [],
  );

  const handleSelect = useCallback(
    (option) => {
      setSelectedStrategy(option);
      onRuleChange(option);
    },
    [onRuleChange],
  );

  return (
    <Form>
      <Form.Item wrapperCol={{ span: 24 }}>
        <Select
          className="attribute-rule__select"
          defaultValue={options[0].value}
          onSelect={handleSelect}
          options={options}
        />
        {LABELS_MAP[selectedStrategy]}
      </Form.Item>
    </Form>
  );
};

export default memo(AttributeRule);
