import * as NextRouter from 'next/router';

export default function mockNextRouter({ query = {} } = {}) {
  const mock = {
    back: jest.fn(),
    push: jest.fn(),
    replace: jest.fn(),
    useRouter: jest.fn(),
  };

  NextRouter.mock = mock;

  NextRouter.useRouter = mock.useRouter;
  NextRouter.useRouter.mockImplementation(() => ({
    back: mock.back,
    push: mock.push,
    replace: mock.replace,
    query,
  }));

  return NextRouter;
}
