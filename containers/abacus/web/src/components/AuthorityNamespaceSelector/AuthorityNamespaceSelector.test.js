import React from 'react';
import { render, waitFor } from '@testing-library/react';
import { testIds } from './AuthorityNamespaceSelectorWrap';
import AuthorityNamespaceSelector from './index';

jest.mock('@/helpers/requestClient');

describe('<AuthorityNamespaceSelector />', () => {
  it('should render authority namespace selector', async () => {
    const { getByTestId } = render(<AuthorityNamespaceSelector />);
    waitFor(() => {
      expect(getByTestId(testIds._)).toHaveTextContent('Authority Namespace');
    });
  });
});
