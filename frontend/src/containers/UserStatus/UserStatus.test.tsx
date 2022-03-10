import { render, screen, fireEvent } from "@testing-library/react";
import UserStatus from "./UserStatus";
import {saveNewRealm} from "./utils";
const { ReactKeycloakProvider } = require('@react-keycloak/web')

const mockKeycloak = ()=>({
  init: jest.fn().mockResolvedValue(true),
  login: jest.fn(),
  logout: jest.fn(),
  createLoginUrl: jest.fn(),
  authenticated: false,
  initialized: true
});

describe('UserStatus component', () => {
  beforeEach(()=>{
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
  });
  it("renders log in btn, when logged out", () => {
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
    fireEvent.click(element);
    expect(mockKeycloakStub.login).toHaveBeenCalled();
  });

  it("renders log out btn, when logged in", () => {
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
    fireEvent.click(element);
    expect(mockKeycloakStub.logout).toHaveBeenCalled();
  });

  it("should save realm in localStorage",()=> {
    Object.defineProperty(window, "localStorage", {
      value: {
        getItem: jest.fn(() => null),
        setItem: jest.fn(() => null)
      },
      writable: true
    });
    const mockKeycloak = {
      logout: () => {
      },
      authenticated: true
    };
    saveNewRealm(mockKeycloak, "value");
    expect(window.localStorage.setItem).toHaveBeenCalledWith("realm-tmp", "value");
    saveNewRealm({...mockKeycloak, authenticated: false}, "value");
    expect(window.localStorage.setItem).toHaveBeenCalledWith("realm", "value");
  });
});
