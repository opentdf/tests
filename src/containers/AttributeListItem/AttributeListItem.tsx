import { FC, useCallback, useMemo, useState } from "react";
import { List, Table, Divider } from "antd";
import { toast } from "react-toastify";

import {AttributeDefinition, AuthorityDefinition, RuleEnum} from "../../types/attributes";
import { Entitlements } from "../../types/entitlements";
import { Method } from "../../types/enums";

import { entityClient } from "../../service";
import { useLazyFetch } from "../../hooks";
import { TABLE_COLUMNS } from "./constants";

import { AttributeRule, OrderCard, OrderList } from "../../components";

type Props = {
  activeAuthority: AuthorityDefinition;
  attr: AttributeDefinition;
};

// @ts-ignore
const serverData = window.SERVER_DATA;

const AttributeListItem: FC<Props> = (props) => {
  const { attr, activeAuthority } = props;
  const { name, order, state } = attr;

  const [activeTabKey, setActiveTab] = useState("");
  const [isEdit, setIsEdit] = useState(false);
  const [activeOrderList, setActiveOrderList] = useState<string[]>([]);
  const [activeAttribute, setActiveAttribute] = useState<AttributeDefinition>({
    authority: "",
    name: "",
    order: [],
    rule: "allOf",
    state: ""
  });
  const [activeRule, setActiveRule] = useState<RuleEnum>("allOf");

  const [getAttrEntities, { loading, data: entities }] =
    useLazyFetch<Entitlements[]>(entityClient);
  const [updateRules] = useLazyFetch(entityClient);

  const toggleEdit = useCallback(() => {
    setIsEdit(!isEdit);
  }, [isEdit]);

  const activeOrderItem = useMemo(
    () => order.find((orderItem: string) => orderItem === activeTabKey),
    [activeTabKey, order],
  );

  const tabList = useMemo(
    () =>
      order.map((orderItem: string) => ({
        key: orderItem,
        tab: orderItem,
      })),
    [order],
  );

  const handleOrderClick = useCallback(
    async (attribute: AttributeDefinition, orderItem: string) => {
      const { authority, name } = attribute;

      const path = encodeURIComponent(
        `${authority}/attr/${name}/value/${orderItem}`,
      );

      try {
        await getAttrEntities({
          method: Method.GET,
          path: serverData.attributes + `/entitlements/${path}`,
        });
      } catch (error) {
        toast.error("Could not get entities");
      }

      setActiveTab(orderItem);
      setActiveOrderList(attribute.order);
      setActiveAttribute(attribute);
    },
    [getAttrEntities],
  );

  const handleTabChange = useCallback(
    (tab: string) => {
      handleOrderClick(attr, tab);
    },
    [attr, handleOrderClick],
  );

  const handleSaveClick = useCallback(async () => {
    const data: AttributeDefinition = {
      authority: activeAuthority.authority,
      name: activeAttribute.name,
      order: activeOrderList,
      rule: activeRule,
      state: activeAttribute?.state,
    };

    try {
      await updateRules({
        method: Method.PUT,
        path: serverData.attributes + `/attributes`,
        data,
      });

      toast.success("Rule was updated!");
    } catch (error) {
      toast.error("Could not update rules!");
    }
  }, [
    activeAttribute,
    activeAuthority,
    activeOrderList,
    activeRule,
    updateRules,
  ]);

  const handleRuleChange = useCallback((rule) => {
    setActiveRule(rule);
  }, []);

  const handleReorder = useCallback((list) => {
    setActiveOrderList(list);
  }, []);

  const handleClose = useCallback(() => {
    setActiveTab("");
  }, []);

  return (
    <List.Item>
      <OrderCard
        activeTabKey={activeTabKey}
        isActive={!!activeOrderItem}
        isEdit={!!activeOrderItem && isEdit}
        name={name}
        onClose={handleClose}
        onSaveClick={handleSaveClick}
        onTabChange={handleTabChange}
        state={state}
        tabList={tabList}
        toggleEdit={toggleEdit}
      >
        {activeOrderItem && (
          <>
            <Table
              className="table"
              columns={TABLE_COLUMNS}
              dataSource={entities}
              loading={loading}
            />

            {isEdit && (
              <>
                <Divider orientation="left">Edit rule</Divider>

                <AttributeRule onRuleChange={handleRuleChange} />

                <div>
                  <OrderList list={activeOrderList} onReorder={handleReorder} />
                </div>
              </>
            )}
          </>
        )}
      </OrderCard>
    </List.Item>
  );
};

export default AttributeListItem;
