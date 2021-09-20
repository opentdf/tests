import { requestEntities } from '@/__fixtures__/requestData';

export const jestFn = jest.fn();
export const useReducerAsyncMock = jest.fn();
useReducerAsyncMock.mockImplementation(() => [requestEntities, jestFn]);
export const useReducerAsync = useReducerAsyncMock;
