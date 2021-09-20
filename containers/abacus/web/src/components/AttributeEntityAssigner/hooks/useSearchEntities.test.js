import { renderHook } from '@testing-library/react-hooks';
import generateClient from '@/helpers/requestClient';
import { requestEntities } from '@/__fixtures__/requestData';
import useSearchEntities, { STATES } from './useSearchEntities';

jest.mock('@/helpers/requestClient');

const { mockClient } = generateClient;

test('shouldnt fetch if query is not defined', async () => {
  const { result } = renderHook(() => useSearchEntities());

  expect(result.current.state).toBe(false);
});

test('should set data and state', async () => {
  const { result, waitForNextUpdate } = renderHook(() => useSearchEntities('q'));

  expect(result.current.state).toBe(STATES.LOADING);

  await waitForNextUpdate();

  expect(mockClient).toHaveBeenCalledTimes(1);
  expect(mockClient).toHaveBeenCalledWith('src.web.entity.find', [{ q: 'q' }]);
  expect(result.current.state).toBe(STATES.SUCCESS);
  expect(result.current.entities).toHaveLength(requestEntities.length);
  expect(result.current.entities.map(({ props }) => props)).toEqual(requestEntities);
});

test('should set failure state', async () => {
  generateClient.mockClient.mockOverrideDefaultResolveValue().mockReturnValue(1);
  const { result, waitForNextUpdate } = renderHook(() => useSearchEntities('okay'));

  await waitForNextUpdate();

  expect(result.current.state).toBe(STATES.FAILURE);
});
