// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

beforeEach(() => {
  const mockKeycloakStub = {
    init: jest.fn().mockResolvedValue(true),
    login: jest.fn(),
    logout: jest.fn(),
    createLoginUrl: jest.fn(),
    authenticated: true,
    initialized: true
  };

  jest.mock("@react-keycloak/web", () => ({
    useKeycloak: () => ({ keycloak: mockKeycloakStub })
  }))
})

// @ts-ignore
global.SERVER_DATA = {
  attributes: 'https://opentdf.us/v2/attributes',
  entitlements: 'https://opentdf.us/v2/entitlements',
  authority: 'https://keycloak.opentdf.us/auth/',
  clientId: 'localhost-abacus',
  access: 'https://opentdf.us/kas',
  realms: ['opentdf-realm', 'opentdf-realm-1']
}