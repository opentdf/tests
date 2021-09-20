const path = require('path');

const SRC_PATH = path.resolve(__dirname, '../src');
const PRJ_ROOT_PATH = path.resolve(__dirname, '../../../');

module.exports = {
  addons: ['@storybook/addon-knobs'],
  webpackFinal: async (baseConfig, options) => {
    // Modify or replace config. Mutating the original reference object can cause unexpected bugs.
    const { module = {} } = baseConfig;

    const newConfig = {
      ...baseConfig,
      module: {
        ...module,
        // Exclude Storybook css processing
        rules: module.rules.filter(rule => {
          if (rule && rule.test && typeof rule.test.test === 'function') {
            return !rule.test.test('styles.css');
          } else {
            return false;
          }
        })
      },
      externals: {
        fs: 'empty', path: 'empty'
      }
    };

    newConfig.resolve = {
      alias: {
        '@': SRC_PATH,
        "@easRoot": path.resolve(PRJ_ROOT_PATH, 'eas'),
      },
      extensions: ['.js', '.jsx', '.css', '.png', '.jpg', '.gif', '.jpeg', '.svg']
    };

    // Add SVGR Loader: https://duncanleung.com/import-svg-storybook-webpack-loader/
    // ========================================================
    const svgAssetRule = newConfig.module.rules.find(({ test }) => test.test(".svg"));

    // Merge our rule with existing assetLoader rules
    newConfig.module.rules.unshift({
      test: /\.svg$/,
      use: [
        "@svgr/webpack", 
        {
          loader: svgAssetRule.loader,
          options: svgAssetRule.options || svgAssetRule.query,
        }
      ],
    });


    //
    // CSS Modules
    // Many thanks to https://github.com/storybookjs/storybook/issues/6055#issuecomment-521046352
    //

    // First we prevent webpack from using Storybook CSS rules to process CSS modules
    // newConfig.module.rules.find(
    //   rule => rule.test.toString() === '/\\.css$/'
    // ).exclude = /\.module\.css$/;

    // newConfig = newConfig.module.rules.filter(rule => {
    //   if (rule && rule.test && typeof rule.test.test === 'function') {
    //     return !rule.test.test('styles.css');
    //   } else {
    //     return false;
    //   }
    // });

    // Then we tell webpack what to do with CSS modules
    newConfig.module.rules.push({
      test: /\.module.css$/,
      include: [SRC_PATH],
      use: [
        {
          loader: 'style-loader'
        },
        {
          loader: 'css-loader',
          options: {
            sourceMap: true,
            importLoaders: 1,
            modules: true
          }
        },
        {
          loader: 'postcss-loader',
          options: {
            sourceMap: true,
            config: {
              path: './.storybook/'
            }
          }
        }
      ]
    });

    newConfig.module.rules.push({
      test: /\.(png|jpg|gif|woff|woff2|eot|ttf)$/,
      use: [
        {
          loader: 'url-loader',
          options: {
            limit: 8192,
            fallback: 'file-loader'
          }
        }
      ]
    });

    newConfig.module.rules.push({
      test: /\.ya?ml$/,
      use: 'js-yaml-loader',
    });

    return newConfig;
  }
};
