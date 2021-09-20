module.exports = {
  preset: 'jest-puppeteer',
  moduleNameMapper: {
    '^@easRoot/(.*)$': '<rootDir>../../../eas/$1',
  },
  testPathIgnorePatterns: ['/node_modules/', '/.next/'],
  testRegex: '(test|spec)\\.js$',
  transform: {
    '^.+\\.(js|jsx|ts|tsx)$': '../node_modules/babel-jest',
    // '^.+\\.css$': '<rootDir>/config/jest/cssTransform.js',
  },
};
