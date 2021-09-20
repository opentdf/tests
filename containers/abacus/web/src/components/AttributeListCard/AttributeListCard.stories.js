import React from 'react';
import Container from '@/helpers/storybookContainer';
import { RuleAccessType } from '@/helpers/attributeRuleTypes';
import AttributeList from '.';

export default {
  title: 'Attribute List',
  component: AttributeList,
};

const attrObj = {
  authorityNamespace: 'https://eas.eternos.xyz',
  name: 'SCIControls',
  order: ['SI', 'TK', 'GAMMAZZYY', 'GAMMANEMO'],
  rule: 'allOf',
  state: 'active',
};

const order = ['SI', 'TK', 'GAMMAZZYY', 'GAMMANEMO'];
const hierarchyAttrObj = {
  authorityNamespace: 'https://eas.eternos.xyz',
  name: 'SCIControls',
  order: [...order],
  rule: RuleAccessType.HIERARCHICAL,
  state: 'active',
};

const emptyAttrObj = {
  authorityNamespace: 'https://eas.eternos.xyz',
  name: 'SCIControls',
  order: [],
  rule: 'allOf',
  state: 'active',
};
const ns = 'https://eas.eternos.xyz';
// eslint-disable-next-line no-unused-vars
const change = (a, b, c) => {};

export const AttributeListWithItems = () => (
  <Container>
    <AttributeList
      namespace={ns}
      attributeName={attrObj.name}
      ruleType={attrObj.rule}
      onOrderChange={change}
      orderList={attrObj.order}
      attributeObject={attrObj}
      attributeRule={attrObj}
    />
  </Container>
);

export const HierarchyAttributeListWithItems = () => (
  <Container>
    <AttributeList
      namespace={ns}
      attributeName={hierarchyAttrObj.name}
      ruleType={hierarchyAttrObj.rule}
      onOrderChange={change}
      orderList={hierarchyAttrObj.order}
      attributeObject={hierarchyAttrObj}
      attributeRule={hierarchyAttrObj}
    />
  </Container>
);

export const EmptyAttributeList = () => (
  <Container>
    <AttributeList
      namespace={ns}
      attributeName={emptyAttrObj.name}
      ruleType={emptyAttrObj.rule}
      onOrderChange={change}
      orderList={emptyAttrObj.order}
      attributeObject={emptyAttrObj}
      attributeRule={emptyAttrObj}
    />
  </Container>
);
