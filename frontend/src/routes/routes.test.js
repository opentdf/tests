import * as routes from './index';

describe('Routes file', () => {
  it('exports valid routes', () => {
    expect(routes.ATTRIBUTES).toEqual('/attributes');
    expect(routes.ATTRIBUTE).toEqual('/attributes/:id');
    expect(routes.CATCH).toEqual('*');
    expect(routes.ENTITLEMENTS).toEqual('/entitlements');
    expect(routes.CLIENTS).toEqual('/entitlements/clients');
    expect(routes.CLIENT).toEqual('/entitlements/clients/:id');
    expect(routes.HOME).toEqual('/');
    expect(routes.USERS).toEqual('/entitlements/users');
    expect(routes.USER).toEqual('/entitlements/users/:id');
    expect(routes.routes).toMatchObject({
      ATTRIBUTE: '/attributes/:id',
      ATTRIBUTES: '/attributes',
      CATCH: '*',
      CLIENT: '/entitlements/clients/:id',
      CLIENTS: '/entitlements/clients',
      ENTITLEMENTS: '/entitlements',
      HOME: '/',
      USER: '/entitlements/users/:id',
      USERS: '/entitlements/users'
    });
  });
});