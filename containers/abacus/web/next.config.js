const { version } = require('./package.json');

module.exports = {
  basePath: process.env.NEXT_BASE_PATH || '',
  assetPrefix: process.env.NEXT_ASSET_PREFIX || '/',
  // eslint-disable-next-line no-unused-vars
  async exportPathMap(defaultPathMap, { dev, dir, outDir, distDir, buildId }) {
    return {
      '/': { page: '/' },
      '/attributes': { page: '/attributes' },
    };
  },
  webpack(config, { buildId, webpack }) {
    const nextConfig = config;

    // Yaml loader for OpenAPI schemas
    nextConfig.module.rules.push({
      test: /\.ya?ml$/,
      use: 'js-yaml-loader',
    });

    // Fix for modules which require node apis but don't use them
    nextConfig.node = { ...config.node, fs: 'empty', path: 'empty' };

    nextConfig.plugins.push(
      new webpack.DefinePlugin({
        'process.env.CONFIG_BUILD_ID': JSON.stringify(buildId),
        'process.env.PKG_VERSION': JSON.stringify(version),
      }),
      // Ignore tests during build
      new webpack.IgnorePlugin(/(\/__tests__\/.*|(\.|\/)(test|spec))\.[jt]sx?$/),
      // Ignore storybook stories
      new webpack.IgnorePlugin(/\.stories\.js$/),
    );

    return nextConfig;
  },
};
