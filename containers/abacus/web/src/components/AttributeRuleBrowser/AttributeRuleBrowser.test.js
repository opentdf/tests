import { render, waitFor } from '@testing-library/react';
import { requestAttributes } from '@/__fixtures__/requestData';
import useAttributeRules from '@/hooks/useAttributeRules';
import AttributeRuleBrowser, { testIds } from './AttributeRuleBrowser';

function renderComponent(props) {
  return render(<AttributeRuleBrowser {...props} />);
}

jest.mock('@/hooks/useAttributeRules', () => jest.fn());

describe('<AttributeRuleBrowser />', () => {
  it('should render without attribute rule cards', async () => {
    const { getByTestId, queryByTestId } = renderComponent();
    await waitFor(() => {
      expect(getByTestId(testIds._)).toBeInTheDocument();
      expect(queryByTestId(testIds.card)).not.toBeInTheDocument();
    });
  });

  it('should not render bad data', async () => {
    const { getByTestId, queryByTestId } = renderComponent();
    await waitFor(() => {
      expect(getByTestId(testIds._)).toBeInTheDocument();
      expect(queryByTestId(testIds.card)).not.toBeInTheDocument();
    });
  });

  it('should render with attribute rule cards', async () => {
    const attributeRulesFormatted = requestAttributes;

    useAttributeRules.mockImplementation(() => attributeRulesFormatted);

    const { getAllByTestId } = renderComponent();
    expect(getAllByTestId(testIds.card).length).toEqual(attributeRulesFormatted.length);
  });
});
