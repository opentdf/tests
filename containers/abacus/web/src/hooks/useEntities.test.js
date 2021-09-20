import { renderHook } from '@testing-library/react-hooks';
import { requestEntities } from '@/__fixtures__/requestData';
import useEntities from './useEntities';

jest.mock('@/helpers/requestClient');

test('should set attribute rules', async () => {
  const { result, waitForNextUpdate } = renderHook(() => useEntities());
  await waitForNextUpdate();
  expect(result.current).toEqual(requestEntities);
});
