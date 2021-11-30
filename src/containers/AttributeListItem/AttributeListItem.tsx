import { FC, useCallback, useMemo, useState } from "react";
import { List, Table, Divider } from "antd";

import { Attribute } from "../../types/attributes";
import { EntityAttribute } from "../../types/entitlements";
import { Method } from "../../types/enums";

import { entityClient } from "../../service";
import { useLazyFetch } from "../../hooks";
import { TABLE_COLUMNS } from "./constants";

import { AttributeRule, OrderCard, OrderList } from "../../components";

type Props = {
  activeAuthority: string;
  attr: Attribute;
};

const AttributeListItem: FC<Props> = (props) => {
  const { attr, activeAuthority } = props;
  const { name, order, state } = attr;

  const [activeTabKey, setActiveTab] = useState("");
  const [isEdit, setIsEdit] = useState(false);
  const [activeOrderList, setActiveOrderList] = useState<string[]>([]);
  const [activeAttribute, setActiveAttribute] = useState<Attribute>();
  const [activeRule, setActiveRule] = useState();

  const [getAttrEntities, { loading, data: entities }] =
    useLazyFetch<EntityAttribute[]>(entityClient);
  const [updateRules] = useLazyFetch(entityClient);

  const toggleEdit = useCallback(() => {
    setIsEdit(!isEdit);
  }, [isEdit]);

  const activeOrderItem = useMemo(
    () => order.find((orderItem) => orderItem === activeTabKey),
    [activeTabKey, order],
  );

  const tabList = useMemo(
    () =>
      order.map((orderItem) => ({
        key: orderItem,
        tab: orderItem,
      })),
    [order],
  );

  const handleOrderClick = useCallback(
    (attribute: Attribute, orderItem: string) => {
      const { authorityNamespace, name } = attribute;

      const path = encodeURIComponent(
        `${authorityNamespace}/attr/${name}/value/${orderItem}`,
      );

      getAttrEntities({
        method: Method.GET,
        path: `/entitlement/v1/attribute/${path}/entity/`,
      });

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

  const handleSaveClick = useCallback(() => {
    const params = {
      authorityNamespace: activeAuthority,
      name: activeAttribute?.name,
      order: activeOrderList,
      rule: activeRule,
      state: activeAttribute?.state,
    };

    updateRules({
      method: Method.PUT,
      path: `/attributes/v1/attr`,
      params,
    });
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
