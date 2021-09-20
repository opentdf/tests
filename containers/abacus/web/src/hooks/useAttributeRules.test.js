import { renderHook } from '@testing-library/react-hooks';
import generateClient from '@/helpers/requestClient';
import { requestAttributes } from '@/__fixtures__/requestData';
import useAttributeRules from './useAttributeRules';

jest.mock('@/helpers/requestClient');

describe('useAttributeRules', () => {
  beforeEach(() => {
    generateClient.mockClient.mockReset();
  });

  it('should set no attribute rules w`hen no selected authority namespace', async () => {
    generateClient.mockClient.mockOverrideDefaultResolveValue().mockResolvedValue({
      data: {},
    });
    const { result, waitForNextUpdate } = renderHook(() => useAttributeRules());
    await waitForNextUpdate();
    expect(result.current).toEqual([]);
  });

  it('should set attribute rules', async () => {
    const { result, waitForNextUpdate } = renderHook(() => useAttributeRules('ns'));
    await waitForNextUpdate();
    expect(result.current).toHaveLength(requestAttributes.length);
  });
});
