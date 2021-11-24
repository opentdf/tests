// TODO Jest isn't liking the dynamic import. Need to investigate further.
// https://stackoverflow.com/questions/46906948/how-to-unit-test-next-js-dynamic-components
/* istanbul ignore file */

// NOTE: Root application for Next.js
// Read more: https://nextjs.org/docs/advanced-features/custom-app
import cookie from 'cookie';
import dynamic from 'next/dynamic';
import { SSRCookies, SSRKeycloakProvider } from '@react-keycloak/ssr';
import 'abort-controller/polyfill';
import useLoader, { Loader } from '@/hooks/useLoader';
import useNewEntity, { EntityContext } from '@/hooks/useNewEntity';
import useAttributeRuleCreate, { AttributeCreateContext } from '@/hooks/useAttributeRuleCreate';
import useAuthorityNamespacesCreate, {
  AuthorityNamespacesCreateContext,
} from '@/hooks/useAuthorityNamespacesCreate';
import KeyCloak from '@/components/KeyCloak';
import 'antd/dist/antd.css';

// Global styles
import './styles.css';
// Virtuoso design tokens
import 'virtuoso-design-system/dist/design_tokens.css';
// Virtuoso component styles
import 'virtuoso-design-system/dist/styles.css';
import { OIDC_BASE_URL } from '@/helpers/requestClient';

const NoSSR = dynamic(() => import('@/components/NoSSR'), { ssr: false });

const keycloakCfg = {
  'public-client': true,
  'ssl-required': 'external',
  clientId: 'tdf-entitlement',
  realm: 'tdf',
  url: OIDC_BASE_URL,
};

const keycloakInitOptions = {
  onLoad: 'login-required',
};

// eslint-disable-next-line react/prop-types
function App({ Component, pageProps, cookies }) {
  const entityProviderValue = useNewEntity();
  const attributeCreateProviderValue = useAttributeRuleCreate();
  const authorityNamespacesCreateProviderValue = useAuthorityNamespacesCreate();
  const loader = useLoader();

  return (
    <SSRKeycloakProvider
      initOptions={keycloakInitOptions}
      keycloakConfig={keycloakCfg}
      persistor={SSRCookies(cookies)}
    >
      <Loader.Provider value={loader}>
        <KeyCloak>
          <EntityContext.Provider value={entityProviderValue}>
            <AttributeCreateContext.Provider value={attributeCreateProviderValue}>
              <AuthorityNamespacesCreateContext.Provider
                value={authorityNamespacesCreateProviderValue}
              >
                {/* We don't support isomorphic rendering */}
                <NoSSR>
                  {/* Typically we don't want to do prop spreading, but this is required here with JSX */}
                  {/* eslint-disable-next-line react/jsx-props-no-spreading */}
                  <Component {...pageProps} />
                </NoSSR>
              </AuthorityNamespacesCreateContext.Provider>
            </AttributeCreateContext.Provider>
          </EntityContext.Provider>
        </KeyCloak>
      </Loader.Provider>
    </SSRKeycloakProvider>
  );
}

function parseCookies(req) {
  if (!req || !req.headers) {
    return {};
  }
  return cookie.parse(req.headers.cookie || '');
}

App.getInitialProps = async (context) => {
  // Extract cookies from AppContext
  return {
    cookies: parseCookies(context?.ctx?.req),
  };
};

export default App;
