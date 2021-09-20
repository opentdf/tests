import React from 'react';
import { renderHook, act } from '@testing-library/react-hooks';
import Router from 'next/router';
import useLoader, { Loader } from './useLoader';

const wrapper = ({ children }) => <Loader.Provider>{children}</Loader.Provider>;

describe('useLoader', () => {
  it('should set from isLoading to not isLoading on complete', async () => {
    const { result } = renderHook(() => useLoader(), { wrapper });
    expect(result.current.isLoading).toEqual(true);

    await act(async () => {
      Router.events.emit('routeChangeComplete');
    });

    expect(result.current.isLoading).toEqual(false);
  });

  it('should set from isLoading to not isLoading on error', async () => {
    const { result } = renderHook(() => useLoader(), { wrapper });
    expect(result.current.isLoading).toEqual(true);

    await act(async () => {
      Router.events.emit('routeChangeError');
    });

    expect(result.current.isLoading).toEqual(false);
  });
});
