export const ATTRIBUTES = '/attributes';
export const ATTRIBUTE = `${ATTRIBUTES}/:id`;
export const CATCH = "*";
export const ENTITLEMENTS = '/entitlements';
export const CLIENTS = `${ENTITLEMENTS}/clients`;
export const CLIENT = `${CLIENTS}/:id`;
export const HOME = '/';
export const USERS = `${ENTITLEMENTS}/users`;
export const USER = `${USERS}/:id`;

export const routes = { ATTRIBUTE, ATTRIBUTES, CATCH, CLIENT, CLIENTS, ENTITLEMENTS, HOME, USER, USERS };
