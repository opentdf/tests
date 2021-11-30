import { Button, Card, Typography } from "antd";
import { FC, useMemo } from "react";

const { Title, Text } = Typography;

type ListItem = {
  key: string;
  tab: React.ReactNode;
};

type Props = {
  activeTabKey: string;
  isActive: boolean;
  isEdit: boolean;
  name: string;
  onClose: () => void;
  onSaveClick: () => void;
  onTabChange: (item: string) => void;
  state?: string;
  tabList: ListItem[];
  toggleEdit: () => void;
};

const OrderCard: FC<Props> = (props) => {
  const {
    activeTabKey,
    isActive,
    isEdit,
    name,
    onClose,
    onSaveClick,
    onTabChange,
    state,
    tabList,
    toggleEdit,
  } = props;

  const actions = useMemo(() => {
    const config = {
      view: [{ onClick: toggleEdit, key: "edit", text: "Edit Rule" }],
      edit: [
        { onClick: onSaveClick, key: "save-rule", text: "Save rule" },
        { onClick: toggleEdit, key: "cancel", text: "Cancel" },
      ],
    };

    if (!isActive && !activeTabKey) {
      return;
    }

    const key = isEdit ? "edit" : "view";

    return config[key].map(({ onClick, key, text }) => (
      <Button onClick={onClick} key={key}>
        {text}
      </Button>
    ));
  }, [activeTabKey, isActive, isEdit, toggleEdit, onSaveClick]);

  const title = useMemo(
    () => (
      <div>
        <Title level={3}>{name}</Title>
        <Text strong>{state}</Text>
        <Text type="secondary"> Access</Text>
      </div>
    ),
    [name, state],
  );

  const extra = useMemo(() => {
    return isActive && <Button onClick={onClose}>Close</Button>;
  }, [isActive, onClose]);

  return (
    <Card
      actions={actions}
      activeTabKey={activeTabKey}
      extra={extra}
      onTabChange={onTabChange}
      tabList={tabList}
      title={title}
    >
      {props.children}
    </Card>
  );
};

export default OrderCard;
