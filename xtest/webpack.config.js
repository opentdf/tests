const path = require("path");

module.exports = {
  entry: "./sdk/js/browser/utils/oss-encrypt-decrypt-script.js",
  target: "web",
  devtool: "source-map",
  output: {
    filename: "tdf3.js",
    path: path.resolve(__dirname, "sdk/js/browser/dist")
  },
  node: {
    fs: "empty"
  }
};
