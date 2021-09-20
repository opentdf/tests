import React from 'react';
import { render } from '@testing-library/react';
import mockNextRouter from '@/test/helpers/mockNextRouter';
import AttributeValuePage from '@/pages/attributes/[ns]/attr/[attrName]/value';

describe('<AttributeValuePage />', () => {
  it('should redirect within 5 seconds', async () => {
    mockNextRouter({ ns: 'ns', attrName: 'attrName', attrValue: 'attrValue' });
    const { getByText } = render(<AttributeValuePage />);

    expect(getByText(/Redirecting to/)).toBeInTheDocument();
  });
});
