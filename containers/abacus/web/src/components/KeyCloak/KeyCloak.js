import { useEffect } from 'react';
import PropTypes from 'prop-types';
import { useKeycloak } from '@react-keycloak/ssr';
import { KeyCloakContext, useKeyCloakReducer } from '@/hooks/useKeyCloak';

const KeyCloak = ({ children }) => {
  const { keycloak, initialized } = useKeycloak();
  const [state, dispatch] = useKeyCloakReducer();

  useEffect(() => {
    if (initialized && !keycloak.authenticated) {
      return keycloak.login();
    }

    return window.sessionStorage.setItem('keycloak-token', keycloak.token);
  }, [initialized, keycloak.authenticated, keycloak]);

  return (
    <KeyCloakContext.Provider value={[state, dispatch, keycloak]}>
      {children}
    </KeyCloakContext.Provider>
  );
};

KeyCloak.propTypes = {
  children: PropTypes.node,
};

KeyCloak.defaultProps = {
  children: null,
};

export default KeyCloak;
