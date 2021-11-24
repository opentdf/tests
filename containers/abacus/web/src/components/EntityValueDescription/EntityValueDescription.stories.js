/* eslint-disable import/no-extraneous-dependencies */
import { withKnobs, text } from '@storybook/addon-knobs';
import Container from '@/helpers/storybookContainer';
import EntityValueDescription from '.';

export default {
  title: 'Entity Value Description',
  decorators: [withKnobs],
};

export const SingleCard = () => (
  <Container>
    <EntityValueDescription
      name={text('Common Name', 'Name')}
      email={text('Email', 'google@gmail.com')}
      userId={text('Distinguished Name', 'Distinguished Name')}
    />
  </Container>
);
