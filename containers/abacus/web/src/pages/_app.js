// TODO Jest isn't liking the dynamic import. Need to investigate further.
// https://stackoverflow.com/questions/46906948/how-to-unit-test-next-js-dynamic-components
/* istanbul ignore file */

// NOTE: Root application for Next.js
// Read more: https://nextjs.org/docs/advanced-features/custom-app
import React from 'react';
import dynamic from 'next/dynamic';
import useLoader, { Loader } from '@/hooks/useLoader';
import useNewEntity, { EntityContext } from '@/hooks/useNewEntity';

// Global styles
import './styles.css';
// Virtuoso design tokens
import 'virtuoso-design-system/dist/design_tokens.css';
// Virtuoso component styles
import 'virtuoso-design-system/dist/styles.css';

const NoSSR = dynamic(() => import('@/components/NoSSR'), { ssr: false });

// eslint-disable-next-line react/prop-types
function App({ Component, pageProps }) {
  const entityProviderValue = useNewEntity();
  const loader = useLoader();
  return (
    <Loader.Provider value={loader}>
      <EntityContext.Provider value={entityProviderValue}>
        {/* We don't support isomorphic rendering */}
        <NoSSR>
          {/* Typically we don't want to do prop spreading, but this is required here with JSX */}
          {/* eslint-disable-next-line react/jsx-props-no-spreading */}
          <Component {...pageProps} />
        </NoSSR>
      </EntityContext.Provider>
    </Loader.Provider>
  );
}

export default App;
