import {
  AutoComplete as AntdAutoComplete,
  AutoCompleteProps,
  Form,
} from "antd";
import { useCallback, useEffect, useState } from "react";

const AutoComplete = (props: AutoCompleteProps & { name: string }) => {
  const {
    defaultActiveFirstOption,
    disabled,
    placeholder,
    style,
    options,
    onSelect,
    name,
  } = props;

  const [componentOptions, setComponentOptions] = useState(options);

  useEffect(() => {
    setComponentOptions(options);
  }, [options]);

  const onSearch = useCallback(
    (searchVal) => {
      const filteredOptions = options?.filter((option) =>
        option.value.match(new RegExp(searchVal, "gi")),
      );

      setComponentOptions(filteredOptions);
    },
    [options],
  );

  return (
    <Form.Item name={name}>
      <AntdAutoComplete
        defaultActiveFirstOption={defaultActiveFirstOption}
        disabled={disabled}
        onSearch={onSearch}
        onSelect={onSelect}
        options={componentOptions}
        placeholder={placeholder}
        style={style}
      />
    </Form.Item>
  );
};

export default AutoComplete;
