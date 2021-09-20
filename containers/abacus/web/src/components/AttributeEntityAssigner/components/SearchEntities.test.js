import React from 'react';
import { act, render, fireEvent, waitFor } from '@testing-library/react';
import SearchEntities, { testIds } from './SearchEntities';

describe('<SearchEntities />', () => {
  const onSearch = jest.fn();

  beforeEach(() => {
    onSearch.mockClear();
  });

  it('should render search field', () => {
    const { getByTestId } = render(<SearchEntities onSearch={onSearch} />);
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByTestId(testIds.input)).toBeInTheDocument();
    expect(getByTestId(testIds.button)).toHaveTextContent('Search');
    expect(getByTestId(testIds.button)).toHaveAttribute('disabled');
  });

  it('should render searching state', () => {
    const { getByTestId } = render(<SearchEntities onSearch={onSearch} isSearching />);
    expect(getByTestId(testIds._)).toBeInTheDocument();
    expect(getByTestId(testIds.button)).toHaveTextContent('...');
    expect(getByTestId(testIds.button)).toHaveAttribute('disabled');
  });

  it('should update on change', async () => {
    const searchValue = 'test';
    const { getByTestId } = render(<SearchEntities onSearch={onSearch} />);

    expect(getByTestId(testIds.button)).toHaveTextContent('Search');

    await act(async () =>
      fireEvent.change(getByTestId(testIds.input), { target: { value: searchValue } })
    );

    expect(getByTestId(testIds.input)).toHaveValue(searchValue);

    await waitFor(() => {
      expect(getByTestId(testIds.button)).not.toHaveAttribute('disabled');
    });

    await act(async () => fireEvent.click(getByTestId(testIds.button)));

    expect(onSearch).toHaveBeenCalledTimes(1);
    expect(onSearch).toHaveBeenCalledWith(searchValue);
  });
});
