import { renderHook, act } from '@testing-library/react-hooks';
import generateClient from '@/helpers/requestClient';
import useAssignEntityToAttribute, { STATES } from './useAssignEntityToAttribute';

jest.mock('@/helpers/requestClient');

const { mockClient } = generateClient;

test('should be initial state - undefined', () => {
  const { result } = renderHook(() => useAssignEntityToAttribute());
  expect(result.current.state).toBe(undefined);
});

test('should set data and state', async () => {
  const namespace = 'namespace';
  const attrName = 'attrName';
  const attrValue = 'attrValue';
  const entityId = 'entityId';
  const onSuccess = jest.fn(() => {});
  const { result, waitForNextUpdate } = renderHook(() =>
    useAssignEntityToAttribute(namespace, attrName, attrValue, { onSuccess })
  );

  act(() => result.current.setEntityId(entityId));

  expect(mockClient).toHaveBeenCalledTimes(1);

  await waitForNextUpdate();

  expect(mockClient).toHaveBeenCalledTimes(2);
  expect(
    mockClient
  ).toHaveBeenCalledWith('src.web.entity_attribute.add_attribute_to_entity_via_attribute', [
    { attributeURI: `${namespace}/attr/${attrName}/value/${attrValue}` },
    [entityId],
  ]);
  expect(result.current.state).toBe(STATES.SUCCESS);
});

test('should set failure state', async () => {
  generateClient.mockClient.mockOverrideDefaultResolveValue().mockRejectedValue(1);
  const { result, waitForNextUpdate } = renderHook(() => useAssignEntityToAttribute());

  act(() => result.current.setEntityId(1));

  await waitForNextUpdate();

  expect(result.current.state).toBe(STATES.FAILURE);
});
