/* eslint-disable import/no-extraneous-dependencies */
const path = require('path');
const webpack = require('webpack');

const SRC_PATH = path.resolve(__dirname, '../src');
const ROOT_PATH = path.resolve(__dirname, '../../..');
const EAS_PATH = path.resolve(ROOT_PATH, 'eas');

module.exports = {
  entry: './integrationTests/requestClientTest/requestClientTest',
  target: 'web',
  devtool: 'source-map',
  output: {
    filename: 'clientTestBundle.js',
    path: path.resolve(__dirname, '../integrationTests/requestClientTest/dist'),
  },
  resolve: {
    alias: {
      '@': SRC_PATH,
      '@easRoot': EAS_PATH,
    },
  },
  node: {
    fs: 'empty',
  },
  module: {
    rules: [
      {
        test: /\.ya?ml$/,
        use: 'js-yaml-loader',
      },
    ],
  },
  plugins: [
    new webpack.DefinePlugin({
      'process.env.EAS_URL': 'https://etheria.local/eas/',
      'process.env.KAS_URL': 'https://etheria.local/kas/',
    }),
  ],
};
