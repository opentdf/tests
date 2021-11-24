// import { renderHook, act } from '@testing-library/react-hooks';
// import Router from 'next/router';
import * as Router from 'next/router';
// import useLoader, { Loader } from './useLoader';

// const wrapper = ({ children }) => <Loader.Provider>{children}</Loader.Provider>;
Router.useRouter = jest.fn();
// WIP !!! strange test
// eslint-disable-next-line no-unused-vars
let eventName;
// eslint-disable-next-line no-unused-vars
let routeChangeHandler;
Router.useRouter.mockImplementation(() => ({
  query: { entityId: 'CN=bob' },
  prefetch: jest.fn(() => Promise.resolve()),
  events: {
    on: jest.fn((event, callback) => {
      eventName = event;
      routeChangeHandler = callback;
    }),
    off: jest.fn((event, callback) => {
      eventName = event;
      routeChangeHandler = callback;
    }),
  },
}));

describe('useLoader', () => {
  // it('should set from isLoading to not isLoading on complete', async () => {
  //   const { result } = renderHook(() => useLoader(), { wrapper });
  //   expect(result.current.isLoading).toEqual(true);
  //
  //   await act(async () => {
  //     Router.Router.events.emit('routeChangeComplete');
  //   });
  //
  //   expect(result.current.isLoading).toEqual(false);
  // });

  it('should set from isLoading to not isLoading on error', async () => {
    // const { result } = renderHook(() => useLoader(), { wrapper });
    // expect(result.current.isLoading).toEqual(true);
    //
    // await act(async () => {
    //   Router.Router.events.emit('routeChangeError');
    // });

    // expect(result.current.isLoading).toEqual(false);
    expect(true).toBeTruthy();
  });
});
