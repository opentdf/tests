import generateClient, { SERVICE_EAS } from '@/helpers/requestClient';
import findAndDecorate from '@/helpers/decorateArraysObjectItem';

const client = generateClient(SERVICE_EAS);

const FETCH = 'FETCH';
const DELETE = 'DELETE';
const INACTIVATE_ENTITY = 'INACTIVATE_ENTITY';
const ASSIGN = 'ASSIGN';

export const ACTIONS = { FETCH, DELETE, ASSIGN, INACTIVATE_ENTITY };

// This case is perfect for usereducer
// https://reactjs.org/docs/hooks-reference.html#usereducer
// Except usereducer is not for async stuff, found discussion with Dan Abramov
// https://gist.github.com/astoilkov/013c513e33fe95fa8846348038d8fe42#async-operations-with-usereducer-hook
// He recommended to Use a middleware for dispatch which performs the async
// operation and then calls the actual dispatch
// This module fit perfectly https://github.com/dai-shi/use-reducer-async#usage

export const asyncActionHandlers = {
  [INACTIVATE_ENTITY]: ({ dispatch }) => async ({ entity }) => {
    const inactivateEntity = { ...entity, state: 'inactive' };
    const { data } = await client['src.web.entity.update']([], inactivateEntity);
    dispatch({ type: 'INACTIVATE_ENTITY', data });
  },
  [FETCH]: ({ dispatch }) => async ({ name, value, namespace }) => {
    dispatch({ type: 'FETCH_START' });

    const url =
      name || value || namespace
        ? 'src.web.entity_attribute.get_entities_for_attribute'
        : 'src.web.entity.find';
    const { data } = await client[url]({
      name,
      value,
      namespace,
    });
    dispatch({ type: 'FETCH_END', data });
  },
  [DELETE]: ({ dispatch }) => async ({ attributeURI, entityId }) => {
    dispatch({ type: 'LOADING_ENTITY', entityId });
    try {
      await client['src.web.entity_attribute.delete_attribute_from_entity']({
        entityId,
        attributeURI,
      });
    } catch (e) {
      console.error(e);
    } finally {
      dispatch({ type: 'DELETE_END', entityId });
    }
  },
  [ASSIGN]: ({ dispatch }) => async ({ attributeURI, entityId }) => {
    dispatch({ type: 'LOADING_ENTITY', entityId });
    try {
      await client['src.web.entity_attribute.add_attribute_to_entity_via_attribute'](
        { attributeURI },
        [entityId]
      );
    } catch (e) {
      console.error(e);
    } finally {
      dispatch({ type: 'RESTORE_END', entityId });
    }
  },
};

const loadingState = { decoration: { loading: true } };
const deletedState = { decoration: { isDeleted: true, loading: false } };
const restoredState = { decoration: { isDeleted: false, loading: false } };

export const entitiesReducer = (state, action) => {
  switch (action.type) {
    case 'FETCH_START':
      return state.map((entity) => ({ ...entity, ...{ fetching: true } }));
    case 'FETCH_END':
      // filter out inactive
      return action.data.filter((entity) => entity.state !== 'inactive');
    case 'LOADING_ENTITY':
      return findAndDecorate({
        idKey: 'userId',
        idValue: action.entityId,
        arr: state,
        ...loadingState,
      });
    case 'INACTIVATE_ENTITY':
      // data is a single entity, put it in an array
      return [action.data];
    case 'DELETE_END':
      return findAndDecorate({
        idKey: 'userId',
        idValue: action.entityId,
        arr: state,
        ...deletedState,
      });
    case 'RESTORE_END':
      return findAndDecorate({
        idKey: 'userId',
        idValue: action.entityId,
        arr: state,
        ...restoredState,
      });
    default:
      throw new Error(`Invalid Action: ${action.type}`);
  }
};
