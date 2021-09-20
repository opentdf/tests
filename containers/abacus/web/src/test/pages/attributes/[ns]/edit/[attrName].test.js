import React from 'react';
import { render, waitFor } from '@testing-library/react';
import AttrNamePage from '@/pages/attributes/[ns]/edit/[attrName]';
import * as nextRouter from 'next/router';

jest.mock('@/helpers/requestClient');
nextRouter.useRouter = jest.fn();

const ns = 'namespace';
const attrName = 'attributeFooBar';

nextRouter.useRouter.mockImplementation(() => ({
  query: { ns, attrName },
}));

describe('<AttributesPage />', () => {
  it('should render authority namespace selector', async () => {
    const { getByText } = render(<AttrNamePage />);

    await waitFor(() => {
      expect(getByText('Edit rule')).toBeTruthy();
    });
  });
});
