import { createContext, useState, useEffect } from 'react';
import Router from 'next/router';

export const LOAD_STATES = {
  LOADING: 'loading',
  COMPLETE: 'complete',
  ERROR: 'error',
};

export const Loader = createContext(LOAD_STATES.LOADING);

function getRouteChangeHandlers(setLoadState) {
  return {
    start() {
      setLoadState(LOAD_STATES.LOADING);
    },

    complete() {
      setLoadState(LOAD_STATES.COMPLETE);
    },

    error() {
      setLoadState(LOAD_STATES.ERROR);
    },
  };
}

function useLoader() {
  const [state, setState] = useState(LOAD_STATES.LOADING);

  useEffect(() => {
    // Add route change handles to manage loading screen
    const routeChangeHandlers = getRouteChangeHandlers(setState);
    // When DOM ready load page
    Router.ready(routeChangeHandlers.complete);
    // Attach event listeners
    Router.events.on('routeChangeStart', routeChangeHandlers.start);
    Router.events.on('routeChangeComplete', routeChangeHandlers.complete);
    Router.events.on('routeChangeError', routeChangeHandlers.error);

    return () => {
      // Remove route change handles on page unmount
      Router.events.off('routeChangeStart', routeChangeHandlers.start);
      Router.events.off('routeChangeComplete', routeChangeHandlers.complete);
      Router.events.off('routeChangeError', routeChangeHandlers.error);
    };
  }, [setState]);

  return { isLoading: [LOAD_STATES.COMPLETE, LOAD_STATES.ERROR].indexOf(state) === -1 };
}

export default useLoader;
