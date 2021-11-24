import { render, waitFor } from '@testing-library/react';
import AttributesPage from '@/pages/attributes';

jest.mock('@/helpers/requestClient');

describe('<AttributesPage />', () => {
  it('should render authority namespace selector', async () => {
    const { getByText } = render(<AttributesPage />);

    await waitFor(() => {
      expect(getByText('Attributes', { selector: 'li' })).toBeTruthy();
      // NOTE(PLAT-875): Deleted for demo
      // expect(getByText('New Attribute')).toBeTruthy();
      expect(getByText('Authority Namespace')).toBeTruthy();
    });
  });
});
