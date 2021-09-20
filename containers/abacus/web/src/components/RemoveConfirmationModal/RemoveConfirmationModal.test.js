import React from 'react';
import { render } from '@testing-library/react';
import RemoveConfirmationModal, { testIds } from './RemoveConfirmationModal';

describe('<RemoveConfirmationModal />', () => {
  it('should show a remove confirmation modal', () => {
    const onCancel = jest.fn();
    const onRemove = jest.fn();
    const { getByTestId } = render(
      <RemoveConfirmationModal title="Remove this" onCancel={onCancel} onRemove={onRemove} />
    );
    expect(getByTestId(testIds._)).toBeInTheDocument();
  });
});
