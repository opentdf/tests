import { ReactNode } from "react";
import { Typography } from "antd";

const { Text } = Typography;

export const LABELS_MAP: Record<string, ReactNode> = {
  allOf: (
    <Text>
      Entities must have at least
      <Text strong> all of</Text> the same attribute values as data.
    </Text>
  ),
  anyOf: (
    <Text>
      Entities must have <Text strong> any of </Text> the same attribute values
      as data.
    </Text>
  ),
  hierarchy: (
    <Text>
      Entities must be
      <Text strong> higher than or equal to </Text> data in a hierarchy of
      attribute values
    </Text>
  ),
};
