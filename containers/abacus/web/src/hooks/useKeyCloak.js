import { createContext } from 'react';
import { useReducerAsync } from 'use-reducer-async';
import keyCloakAxios from '../helpers/keyCloakAxios';

const GET_USERS = 'GET_USERS';
const GET_USER = 'GET_USER';
const GET_CLIENTS = 'GET_CLIENTS';
const GET_CLIENT = 'GET_CLIENT';
const CLEAN_UP = 'CLEAN_UP';

export const KEYCLOAK_ACTIONS = {
  GET_USERS,
  GET_CLIENTS,
  GET_CLIENT,
  GET_USER,
  CLEAN_UP,
};

const keyCloakPaths = {
  clients: '/admin/realms/tdf/clients',
  users: '/admin/realms/tdf/users',
};

const getClient = async (clientId) => keyCloakAxios.get(`${keyCloakPaths.clients}/${clientId}`);
const getClients = async () => keyCloakAxios.get(keyCloakPaths.clients);
const getUser = async (userId) => keyCloakAxios.get(`${keyCloakPaths.users}/${userId}`);
const getUsers = async () => keyCloakAxios.get(keyCloakPaths.users);

const keycloakReducer = (state, action) => {
  const { type, data } = action;

  const states = new Map([
    ['CLIENT', { ...state, client: data }],
    ['CLIENTS', { ...state, clients: data }],
    ['USER', { ...state, user: data }],
    ['USERS', { ...state, users: data }],
    [KEYCLOAK_ACTIONS.CLEAN_UP, {}],
  ]);

  return states.get(type);
};

const asyncActionHandlers = {
  [GET_USERS]:
    ({ dispatch }) =>
    async () => {
      const { data } = await getUsers();
      dispatch({ type: 'USERS', data });
    },
  [GET_USER]:
    ({ dispatch }) =>
    async (action) => {
      const { data } = await getUser(action.id);
      dispatch({ type: 'USER', data });
    },
  [GET_CLIENTS]:
    ({ dispatch }) =>
    async () => {
      const { data } = await getClients();
      dispatch({ type: 'CLIENTS', data });
    },
  [GET_CLIENT]:
    ({ dispatch }) =>
    async (action) => {
      const { data } = await getClient(action.id);
      dispatch({ type: 'CLIENT', data });
    },
  [CLEAN_UP]:
    ({ dispatch }) =>
    async () => {
      dispatch({ type: 'CLIENT', data: {} });
    },
};

export const useKeyCloakReducer = () => useReducerAsync(keycloakReducer, {}, asyncActionHandlers);

export const KeyCloakContext = createContext({});
