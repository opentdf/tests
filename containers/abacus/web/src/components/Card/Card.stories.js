import React from 'react';
import Container from '@/helpers/storybookContainer';
import Card from '.';

export default {
  title: 'Card',
  component: Card,
};

const title = 'Test Card';
const subtitle = 'Subtitle';
const actions = [
  { key: 'google', children: <a href="https://google.com">Google</a> },
  { key: 'yahoo', children: <a href="https://yahoo.com">Yahoo</a> },
];

export const SingleCard = () => (
  <Container>
    <Card>
      <Card.Header id="header" title={title} actions={actions} />
      Card Content
    </Card>
  </Container>
);

export const CardWithMultipleHeaders = () => (
  <Container>
    <Card>
      <Card.Header id="header" title={title} actions={actions} />
      <Card.Header id="subheader" title={subtitle} actions={actions} />
      Card Content
    </Card>
  </Container>
);
