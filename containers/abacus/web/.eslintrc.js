module.exports = {
  extends: ['airbnb', 'airbnb/hooks', 'plugin:jest/recommended', 'prettier'],
  parser: 'babel-eslint',
  plugins: ['jest', 'jest-dom', 'prettier', 'testing-library'],
  rules: {
    // why? Comply with SonarCloud
    curly: ['error', 'all'],
    // why? Disable due to nextjs Link issue https://github.com/vercel/next.js/issues/5533
    'jsx-a11y/anchor-is-valid': ['off'],
    // why? Need to resolve spreading in the future
    'react/jsx-props-no-spreading': ['warn'],
    'react/jsx-filename-extension': ['warn', { extensions: ['.js', '.jsx'] }],
    'prettier/prettier': ['error'],
  },
  settings: {
    'import/resolver': {
      alias: {
        map: [
          ['@', './src'],
          ['@easRoot', '../../eas'],
        ],
        extensions: ['.ts', '.js', '.jsx', '.json'],
      },
    },
  },
};
