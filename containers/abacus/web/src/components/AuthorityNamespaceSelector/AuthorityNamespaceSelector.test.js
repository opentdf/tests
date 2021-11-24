import { render } from '@testing-library/react';
import { testIds } from './AuthorityNamespaceSelectorWrap';
import AuthorityNamespaceSelector from './index';

jest.mock('@/helpers/requestClient');

describe('<AuthorityNamespaceSelector />', () => {
  it('should render authority namespace selector', async () => {
    // jest.useFakeTimers();
    const { getByTestId } = render(<AuthorityNamespaceSelector />);
    // jest.runAllTimers();
    // waitFor(() => {
    expect(getByTestId(testIds._)).toHaveTextContent('Authority Namespace');
    // });
  });
});
