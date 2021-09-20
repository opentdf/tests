import React from 'react';
import Container from '@/helpers/storybookContainer';
import LinkButton from '.';

export default {
  title: 'LinkButton',
  component: LinkButton,
};

export const DefaultButton = () => (
  <Container>
    {/* eslint-disable-next-line no-undef */}
    <LinkButton onClick={() => alert('Clicked')} text="Click me" />
  </Container>
);
