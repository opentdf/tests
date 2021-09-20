import React from 'react';
import { cleanup, render, getByText as globalGetByText } from '@testing-library/react';

import List from '.';

afterEach(cleanup);

describe('<List />', () => {
  // NOTE(PLAT-875): Deleted for demo
  // eslint-disable-next-line jest/no-disabled-tests
  it.skip('should render empty unordered list', () => {
    const { getByTestId, queryAllByTestId } = render(<List />);
    expect(getByTestId('vds-list-unordered')).toBeInTheDocument();
    expect(queryAllByTestId('vds-list_item').length).toEqual(0);
  });

  it('should render unordered list', () => {
    const { getByTestId, queryAllByTestId } = render(
      <List>
        <List.Item>One</List.Item>
        <List.Item>Two</List.Item>
      </List>
    );
    const listItems = queryAllByTestId('vds-list_item');
    expect(getByTestId('vds-list-unordered')).toBeInTheDocument();
    expect(listItems.length).toEqual(2);
    expect(globalGetByText(listItems[0], 'One')).toBeInTheDocument();
    expect(globalGetByText(listItems[1], 'Two')).toBeInTheDocument();
  });

  it('should render empty ordered list', () => {
    const { getByTestId, queryAllByTestId } = render(<List isOrdered />);
    expect(getByTestId('vds-list-ordered')).toBeInTheDocument();
    expect(queryAllByTestId('vds-list_item').length).toEqual(0);
  });

  it('should render ordered list', () => {
    const { getByTestId, queryAllByTestId } = render(
      <List isOrdered>
        <List.Item>One</List.Item>
        <List.Item>Two</List.Item>
      </List>
    );
    const listItems = queryAllByTestId('vds-list_item');
    expect(getByTestId('vds-list-ordered')).toBeInTheDocument();
    expect(listItems.length).toEqual(2);
    expect(globalGetByText(listItems[0], 'One')).toBeInTheDocument();
    expect(globalGetByText(listItems[1], 'Two')).toBeInTheDocument();
  });
});
