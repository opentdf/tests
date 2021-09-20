import React from 'react';
import Container from '@/helpers/storybookContainer';
import AttributeRuleBrowser from '.';

export default {
  title: 'Attribute Rule Browser',
  component: AttributeRuleBrowser,
};

const kas = 'https://kas.virtru.com';
const values = ['SI', 'TK', 'GAMMA ZZYY', 'GAMMA NEMO'];
const attributes = [
  {
    name: 'SCI Controls',
    accessType: 'restrictive',
    kas,
    values,
  },
  {
    name: 'Sensor NTK',
    accessType: 'permissive',
    kas,
    values,
  },
  {
    name: 'Classification US',
    accessType: 'hierarchical',
    kas,
    values,
  },
];

export const Browser = () => (
  <Container>
    <AttributeRuleBrowser attributes={attributes} />
  </Container>
);
