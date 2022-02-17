import { render, screen } from "@testing-library/react";
import UserStatus from "./UserStatus";
const { ReactKeycloakProvider } = require('@react-keycloak/web')

describe('UserStatus component', () => {
  it("renders log in btn, when logged out", () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: jest.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
    });

    const mockKeycloakStub = {
      init: jest.fn().mockResolvedValue(true),
      login: jest.fn(),
      logout: jest.fn(),
      createLoginUrl: jest.fn(),
      authenticated: false,
      initialized: true
    };

    render(
      <ReactKeycloakProvider authClient={mockKeycloakStub}>
        <UserStatus />
      </ReactKeycloakProvider>
    );
    const element = screen.getByText('Log in');
    expect(element).toBeInTheDocument();
  });

  it("renders log out btn, when logged in", () => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: jest.fn().mockImplementation(query => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: jest.fn(),
        removeListener: jest.fn(),
        addEventListener: jest.fn(),
        removeEventListener: jest.fn(),
        dispatchEvent: jest.fn(),
      })),
    });

    const mockKeycloakStub = {
      init: jest.fn().mockResolvedValue(true),
      login: jest.fn(),
      logout: jest.fn(),
      createLoginUrl: jest.fn(),
      authenticated: true,
      initialized: true
    };

    render(
      <ReactKeycloakProvider authClient={mockKeycloakStub}>
        <UserStatus />
      </ReactKeycloakProvider>
    );
    const element = screen.getByText('Log out');
    expect(element).toBeInTheDocument();
  });
});
