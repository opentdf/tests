import { renderHook } from '@testing-library/react-hooks';
import useAuthorityNamespaces from './useAuthorityNamespaces';
import authorityNamespacesFixtures from './__fixtures__/authorityNamespaces';

jest.mock('@/helpers/requestClient');

test.skip('should set attribute rules', async () => {
  const { result, waitForNextUpdate } = renderHook(() => useAuthorityNamespaces());
  await waitForNextUpdate();
  expect(result.current).toEqual(authorityNamespacesFixtures.allData);
});
