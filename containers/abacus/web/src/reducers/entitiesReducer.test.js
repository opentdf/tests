import { requestEntities } from '@/__fixtures__/requestData';
import { asyncActionHandlers, entitiesReducer, ACTIONS } from './entitiesReducer';

const { FETCH, DELETE, ASSIGN } = ACTIONS;

jest.mock('@/helpers/requestClient');

let dispatcherCalls = [];
let dispatchObj;
const prepareDispatch = (initialState = []) => {
  const dispatch = (...args) =>
    dispatcherCalls.push({
      args,
      returned: entitiesReducer(initialState, ...args),
    });
  dispatchObj = { dispatch };
};
const testedEntityId = 'CN=bob';

describe('entitiesReducer.js', () => {
  beforeEach(() => prepareDispatch());

  afterEach(() => {
    dispatcherCalls = [];
  });

  it('FETCH event should make request fot entities and then call FETCH_END event with data', async () => {
    await asyncActionHandlers[FETCH](dispatchObj)({});
    const { args, returned } = dispatcherCalls[1];
    expect(returned).toEqual(requestEntities);
    expect(args[0]).toEqual({ type: 'FETCH_END', data: requestEntities });
  });

  // eslint-disable-next-line jest/no-disabled-tests
  it.skip('DELETE event should set entity as loading and then as deleted', async () => {
    prepareDispatch(requestEntities);
    await asyncActionHandlers[DELETE](dispatchObj)({ entityId: testedEntityId });

    const { args: loadingArgs, returned: loadingReturned } = dispatcherCalls[0];
    const loadingEntity = loadingReturned.find(({ userId }) => userId === testedEntityId);

    expect(loadingEntity).toEqual({ ...requestEntities[0], loading: true });
    expect(loadingArgs[0]).toEqual({ type: 'LOADING_ENTITY', entityId: testedEntityId });

    const { args: deletingArgs, returned: deletingReturned } = dispatcherCalls[1];
    const deletedEntity = deletingReturned.find(({ userId }) => userId === testedEntityId);

    expect(deletedEntity).toEqual({ ...requestEntities[0], loading: false, isDeleted: true });
    expect(deletingArgs[0]).toEqual({ type: 'DELETE_END', entityId: testedEntityId });
  });

  // eslint-disable-next-line jest/no-disabled-tests
  it.skip('ASSIGN event should set deleted entity as loading and then as assigned', async () => {
    const stateWithDeleted = [{ ...requestEntities[0], loading: false, isDeleted: true }];
    prepareDispatch(stateWithDeleted);
    await asyncActionHandlers[ASSIGN](dispatchObj)({ entityId: testedEntityId });

    const { args: loadingArgs, returned: loadingReturned } = dispatcherCalls[0];
    const loadingEntity = loadingReturned.find(({ userId }) => userId === testedEntityId);

    expect(loadingEntity).toEqual({ ...requestEntities[0], loading: true, isDeleted: true });
    expect(loadingArgs[0]).toEqual({ type: 'LOADING_ENTITY', entityId: testedEntityId });

    const { args: assignArgs, returned: assignReturned } = dispatcherCalls[1];
    const assignedEntity = assignReturned.find(({ userId }) => userId === testedEntityId);

    expect(assignedEntity).toEqual({ ...requestEntities[0], loading: false, isDeleted: false });
    expect(assignArgs[0]).toEqual({ type: 'RESTORE_END', entityId: testedEntityId });
  });
});
