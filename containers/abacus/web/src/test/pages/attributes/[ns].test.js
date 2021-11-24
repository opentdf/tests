import { render } from '@testing-library/react';
import NamespacePage from '@/pages/attributes/[ns]';

describe('<NamespacePage />', () => {
  it('should redirect within 5 seconds', async () => {
    const { getByText } = render(<NamespacePage />);

    expect(getByText(/Redirecting to/)).toBeInTheDocument();
  });
});
