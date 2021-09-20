const path = require('path');
const postcssHexRgba = require('postcss-hexrgba');
const postcssImport = require('postcss-import');
const postcssCustomProperties = require('postcss-custom-properties');

module.exports = {
  modules: true,
  plugins: [
    postcssCustomProperties({
      preserve: false,
      importFrom: [
        'node_modules/virtuoso-design-system/dist/design_tokens.css',
      ],
    }),
    postcssImport(),
    postcssHexRgba,
  ],
};
