import React from 'react';
import { render, waitFor } from '@testing-library/react';
import * as nextRouter from 'next/router';
import AttributeValuesPage from '@/pages/attributes/[ns]/attr/[attrName]';

jest.mock('@/helpers/requestClient');
nextRouter.useRouter = jest.fn();

const ns = 'namespace';
const attrName = 'attributeFooBar';

nextRouter.useRouter.mockImplementation(() => ({
  query: { ns, attrName },
}));

describe('<AttributeValuesPage />', () => {
  it('should render bredcrumbs from url params', async () => {
    const { getByText } = render(<AttributeValuesPage />);
    await waitFor(() => {
      expect(getByText(`Authority Namespace ${ns}`)).toBeTruthy();
      expect(getByText(attrName, { selector: 'li' })).toBeInTheDocument();
    });
  });

  it('shouldnt show details element on this page for card', async () => {
    const { queryByText } = render(<AttributeValuesPage />);
    await waitFor(() => {
      expect(queryByText('Details')).not.toBeInTheDocument();
    });
  });
});
