import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react';
import Pagination, { testIds } from './Pagination';

describe('<Pagination />', () => {
  it('should render component', async () => {
    const onBackClick = jest.fn();
    const onNextClick = jest.fn();

    const { getByTestId } = render(
      <Pagination onBackClick={onBackClick} onNextClick={onNextClick} />
    );
    fireEvent.click(getByTestId(testIds.clickNext));
    fireEvent.click(getByTestId(testIds.clickBack));

    await waitFor(() => expect(onBackClick).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(onNextClick).toHaveBeenCalledTimes(1));
  });
});
