import React from 'react';
import Container from '@/helpers/storybookContainer';
import RuleSandbox from '.';

export default {
  title: 'Rule Sandbox',
  component: RuleSandbox,
};

const examples = {
  'https://example.virtru.com/attr/allOf': {
    authorityNamespace: 'https://kas.virtru.com',
    order: ['A', 'B', 'C', 'D'],
    rule: 'allOf',
  },
  'https://example.virtru.com/attr/anyOf': {
    authorityNamespace: 'https://kas.virtru.com',
    order: ['Ceres', 'Eris', 'Haumea', 'Makemake', 'Pluto'],
    rule: 'anyOf',
  },
  'https://example.virtru.com/attr/hierarchy': {
    authorityNamespace: 'https://kas.virtru.com',
    order: ['TradeSecret', 'Proprietary', 'BusinessSensitive', 'Open'],
    rule: 'hierarchy',
    state: 'active',
  },
};

const pick = (type) => {
  const uri = `https://example.virtru.com/attr/${type}`;
  return { [uri]: examples[uri] };
};

const rsStyle = { backgroundColor: '#deeeff', padding: '12px' };

export const Hierarchical = () => (
  <Container>
    <RuleSandbox style={rsStyle} attribute={pick('hierarchy')} />
  </Container>
);

export const Permissive = () => (
  <Container>
    <RuleSandbox style={rsStyle} attribute={pick('anyOf')} />
  </Container>
);

export const Restrictive = () => (
  <Container>
    <RuleSandbox style={rsStyle} attribute={pick('allOf')} />
  </Container>
);

export const Empty = () => (
  <Container>
    <RuleSandbox style={rsStyle} />
  </Container>
);
