import { Button, Card, Typography } from "antd";
import { FC, useMemo } from "react";

const { Title, Text } = Typography;

type ListItem = {
  key: string;
  tab: React.ReactNode;
};

type Props = {
  activeTabKey: string;
  name: string;
  state?: string;
  tabList: ListItem[];
  onTabChange: (item: string) => void;
  onEditClick: () => void;
};

const OrderCard: FC<Props> = (props) => {
  const { activeTabKey, name, onTabChange, state, tabList, onEditClick } =
    props;

  const actions = useMemo(
    () => [
      <Button onClick={onEditClick} key="edit">
        Edit Rule
      </Button>,
    ],
    [onEditClick],
  );

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

  return (
    <Card
      actions={actions}
      activeTabKey={activeTabKey}
      onTabChange={onTabChange}
      tabList={tabList}
      title={title}
    >
      {props.children}
    </Card>
  );
};

export default OrderCard;
