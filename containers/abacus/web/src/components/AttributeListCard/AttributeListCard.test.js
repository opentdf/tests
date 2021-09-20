import React from 'react';
import { render } from '@testing-library/react';
import { RuleAccessType } from '@/helpers/attributeRuleTypes';
import AttributeList from './AttributeListCard';

describe('<AttributeListCard />', () => {
  const attrObj = {
    authorityNamespace: 'https://eas.eternos.xyz',
    name: 'SCIControls',
    order: ['SI', 'TK', 'GAMMAZZYY', 'GAMMANEMO'],
    rule: RuleAccessType.HIERARCHICAL,
    state: 'active',
  };
  // eslint-disable-next-line no-unused-vars
  const change = (a, b, c) => {};

  it('should render order values in list and sandbox', () => {
    const { getByText } = render(
      <AttributeList
        namespace={attrObj.authorityNamespace}
        attributeName={attrObj.name}
        ruleType={attrObj.rule}
        onOrderChange={change}
        orderList={attrObj.order}
        attributeObject={attrObj}
        attributeRule={attrObj}
      />
    );

    attrObj.order.forEach((name) => {
      expect(getByText(name)).toBeTruthy();
    });
  });
});
