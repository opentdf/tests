import React from 'react';
import { fireEvent, render, waitFor } from '@testing-library/react';
import Link from '@/test/helpers/mockNextLink';
import mockNextRouter from '@/test/helpers/mockNextRouter';
import Redirect, { testIds, REDIRECT_MS } from './Redirect';

const Router = mockNextRouter({});

describe('<Redirect />', () => {
  const href = '/redirect';
  const as = `${href}-as`;

  beforeEach(() => {
    Link.mockClear();
    Router.mock.push.mockReset();
  });

  it('should render a heading and link', () => {
    jest.useFakeTimers();
    const { getByTestId, getByText } = render(<Redirect href={href} />);
    expect(getByText(new RegExp(`Redirecting to ${href}`))).toBeInTheDocument();
    expect(getByTestId(testIds.link)).toBeInTheDocument();
  });

  it(`should redirect in ${REDIRECT_MS}ms`, () => {
    jest.useFakeTimers();
    render(<Redirect href={href} as={as} />);
    jest.runAllTimers();
    expect(setTimeout).toHaveBeenCalledTimes(2);
    expect(setTimeout).toHaveBeenNthCalledWith(2, expect.any(Function), REDIRECT_MS);
    expect(Router.mock.push).toHaveBeenCalledTimes(1);
    expect(Router.mock.push).toHaveBeenCalledWith(href, as);
  });

  it('should redirect on click', async () => {
    jest.useFakeTimers();
    const { getByTestId } = render(<Redirect href={href} as={as} />);
    fireEvent.click(getByTestId(testIds.link));
    await waitFor(() => {
      expect(Link).toHaveBeenCalledTimes(1);
      expect(Link).toHaveBeenLastCalledWith(
        { children: expect.anything(), href, as, shallow: true },
        {}
      );
    });
  });
});
