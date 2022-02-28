const path = require("path");

module.exports = {
  entry: "./sdk/js/web/utils/tdf3-encrypt-decrypt-scripts.js",
  target: "web",
  devtool: "source-map",
  output: {
    filename: "tdf3.js",
    path: path.resolve(__dirname, "sdk/js/web/dist")
  },
  resolve: {
    fallback: {
        "fs": false,
        "stream": false,
        "crypto": false,
        "constants": false
    },
  }
};