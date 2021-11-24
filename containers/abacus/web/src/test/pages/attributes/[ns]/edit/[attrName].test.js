import { render, waitFor } from '@testing-library/react';
import * as nextRouter from 'next/router';
import AttrNamePage from '@/pages/attributes/[ns]/edit/[attrName]';

jest.mock('@/helpers/requestClient');
nextRouter.useRouter = jest.fn();

const ns = 'namespace';
const attrName = 'attributeFooBar';

nextRouter.useRouter.mockImplementation(() => ({
  prefetch: jest.fn(() => Promise.resolve()),
  query: { ns, attrName },
}));

describe('<AttributesPage />', () => {
  it.skip('should render authority namespace selector', async () => {
    const { getByText } = render(<AttrNamePage />);

    await waitFor(() => {
      expect(getByText('Edit rule')).toBeTruthy();
    });
  });
});
