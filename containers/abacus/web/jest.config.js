module.exports = {
  collectCoverageFrom: [
    'src/**/*.{js,jsx,ts,tsx}',
    '!src/**/*.stories.js',
    '!src/**/index.js',
    '!src/components/Virtruoso.js',
    // Ignore test directory, used for helpers
    '!src/test/**',
    // Ignore mock or fixture files
    '!src/**/(__mock__|__fixtures__)/**',
  ],
  // TODO set realistic thresholds for code coverage
  coverageThreshold: {
    global: {
      branches: 71,
      functions: 71,
      lines: 80,
      statements: 80,
    },
  },
  setupFilesAfterEnv: ['./setupTests.js'],
  testPathIgnorePatterns: ['/node_modules/', '/.next/', '/integrationTests/'],
  testRegex: 'src/.*(/__tests__/.*|(\\.|/)(test|spec))\\.[jt]sx?$',
  transform: {
    '\\.ya?ml$': 'yaml-jest',
    '^.+\\.(js|jsx|ts|tsx)$': 'babel-jest',
    // '^.+\\.css$': '<rootDir>/config/jest/cssTransform.js',
  },
  transformIgnorePatterns: ['/node_modules/', '^.+\\.module\\.(css|sass|scss)$'],
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/src/$1',
    '^@easRoot/(.*)$': '<rootDir>/../../eas/$1',
    '^.+\\.module\\.(css|sass|scss)$': 'jest-css-modules-transform',
    '\\.svg': '<rootDir>/src/__mocks__/fileMock.js',
  },
  modulePathIgnorePatterns: [],
};
