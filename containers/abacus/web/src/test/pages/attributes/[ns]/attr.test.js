import React from 'react';
import { render } from '@testing-library/react';
import AttributeNamePage from '@/pages/attributes/[ns]/attr';

describe('<AttributeNamePage />', () => {
  it('should redirect within 5 seconds', async () => {
    const { getByText } = render(<AttributeNamePage />);

    expect(getByText(/Redirecting to/)).toBeInTheDocument();
  });
});
