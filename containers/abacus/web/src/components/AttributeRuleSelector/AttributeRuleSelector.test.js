import { render } from '@testing-library/react';
import { RuleAccessType } from '@/helpers/attributeRuleTypes';
import AttributeRuleSelector from './AttributeRuleSelector';

jest.mock('@/helpers/requestClient');

describe('<AttributeRuleSelector />', () => {
  it('should render with HIERARCHICAL type', async () => {
    const fn = jest.fn();
    const { getByText } = render(
      <AttributeRuleSelector onTypeChange={fn} ruleType={RuleAccessType.HIERARCHICAL} />
    );

    const title = await getByText('Hierarchical Access');

    expect(title).toBeTruthy();
  });
});
