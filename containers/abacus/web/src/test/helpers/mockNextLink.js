import NextLink from 'next/link';

jest.mock('next/link', () => ({
  __esModule: true,
  default: jest.fn(({ children }) => children),
}));

export default NextLink;
