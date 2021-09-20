import { format } from 'util';
// eslint-disable-next-line import/no-extraneous-dependencies
import '@testing-library/jest-dom/extend-expect';

const ignoreErrors = [
  // Ignore HeaderMenus error until resolved in https://github.com/virtru/virtuoso-design-system/pull/80
  /render method of `HeaderMenus`/,
];

global.console.error = (...args) => {
  // Ignore errors that are expected
  if (ignoreErrors.some((pattern) => args.some((arg) => pattern.test(arg)))) {
    return;
  }

  throw new Error(format(...args));
};

global.window = {};

global.matchMedia = {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(), // deprecated
    removeListener: jest.fn(), // deprecated
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
};
Object.defineProperty(global.window, 'matchMedia', global.matchMedia);
