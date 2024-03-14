import React from 'react';
import ReactDOM from 'react-dom/client';
import Keycloak from 'keycloak-js';
import { ReactKeycloakProvider } from '@react-keycloak/web';
import './index.css';
import App from './App';

const keycloak = new Keycloak({
    realm: 'tdf',
    url: 'http://localhost:65432/auth/',
    clientId: 'dcr-test',
});

const root = ReactDOM.createRoot(
  document.getElementById('root') as HTMLElement
);

root.render(
    <ReactKeycloakProvider
      authClient={keycloak}
      initOptions={{
        checkLoginIframe: false,
        responseType: "code id_token token",
        pkceMethod: "S256"
      }}
    >
      <App />
    </ReactKeycloakProvider>
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
