const path = require('path');

// Export a function. Accept the base config as the only param.]
module.exports = {
  stories: [path.resolve(__dirname, '../src/**/*.stories.js')],
  addons: ['@storybook/addon-actions', '@storybook/addon-links'],
  presets: [path.resolve(__dirname, './webpack-preset.js')]
};
