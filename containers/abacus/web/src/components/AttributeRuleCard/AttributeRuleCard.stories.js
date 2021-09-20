import React from 'react';
import Container from '@/helpers/storybookContainer';
import AttributeRuleCard from '.';

export default {
  title: 'Attribute Rule Card',
  component: AttributeRuleCard,
};

const name = 'SCI Controls';
const authorityNamespace = 'https://kas.virtru.com';
const values = ['SI', 'TK', 'GAMMA ZZYY', 'GAMMA NEMO'];

export const SingleCard = () => (
  <Container>
    <AttributeRuleCard
      name={name}
      authorityNamespace={authorityNamespace}
      values={values}
      accessType="restrictive"
      onDetailsAction={() => {}}
      onNewValueAction={() => {}}
      onEditRuleAction={() => {}}
    />
  </Container>
);
