import { toast } from 'react-toastify';
import generateClient, {
  generateKeycloakAuthHeaders,
  SERVICE_EAS,
  SERVICE_ENTITLEMENT,
} from '@/helpers/requestClient';
import findAndDecorate from '@/helpers/decorateArraysObjectItem';

const client = generateClient(SERVICE_EAS);
const entityClient = generateClient(SERVICE_ENTITLEMENT);

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
  [INACTIVATE_ENTITY]:
    ({ dispatch }) =>
    async ({ entity }) => {
      const inactivateEntity = { ...entity, state: 'inactive' };
      const { data } = await client['src.web.entity.update']([], inactivateEntity);
      dispatch({ type: 'INACTIVATE_ENTITY', data });
    },
  [FETCH]:
    ({ dispatch }) =>
    async ({ entityId }) => {
      dispatch({ type: 'FETCH_START' });

      console.log('Fetch Attributes for ', entityId);
      // add attributes fetch anywhere
      const url = entityId
        ? 'read_entity_attribute_relationship_v1_entity__entityId__attribute_get'
        : 'read_relationship_v1_entity_attribute_get';
      const { data } = await entityClient[url](
        { entityId },
        {},
        { headers: generateKeycloakAuthHeaders() }
      );

      dispatch({ type: 'FETCH_END', data });
    },
  [DELETE]:
    ({ dispatch }) =>
    async ({ attributeURI, entityId }) => {
      dispatch({ type: 'LOADING_ENTITY', entityId });

      const headers = generateKeycloakAuthHeaders();

      try {
        await entityClient.delete_attribute_entity_relationship_v1_entity__entityId__attribute__attributeURI__delete(
          {
            entityId,
            attributeURI,
          },
          null,
          { headers }
        );

        const { data } =
          await entityClient.read_entity_attribute_relationship_v1_entity__entityId__attribute_get(
            { entityId },
            {},
            { headers }
          );

        dispatch({ type: 'FETCH_END', data });
        toast.success('Deleted!');
      } catch (e) {
        toast.error('Failed to delete !');
        console.error(e);
      } finally {
        dispatch({ type: 'DELETE_END', entityId });
      }
    },
  [ASSIGN]:
    ({ dispatch }) =>
    async ({ attributeURI, entityId }) => {
      dispatch({ type: 'LOADING_ENTITY', entityId });
      try {
        const headers = generateKeycloakAuthHeaders();

        await entityClient.create_entity_attribute_relationship_v1_entity__entityId__attribute_put(
          { entityId },
          [attributeURI],
          { headers }
        );

        const { data } =
          await entityClient.read_entity_attribute_relationship_v1_entity__entityId__attribute_get(
            { entityId },
            {},
            { headers }
          );

        dispatch({ type: 'FETCH_END', data });
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
      toast.success('Updated!');
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
