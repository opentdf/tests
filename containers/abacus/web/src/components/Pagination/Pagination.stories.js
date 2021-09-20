import React from 'react';
// eslint-disable-next-line import/no-extraneous-dependencies
import { withKnobs, text } from '@storybook/addon-knobs';
import Pagination from './Pagination';

export default {
  title: 'Pagination',
  decorators: [withKnobs],
};

export const DefaultPagination = () => (
  <div style={{ display: 'flex', justifyContent: 'center' }}>
    <Pagination from={text('from', '1')} to={text('to', '20')} of={text('of', '40')} />
  </div>
);
