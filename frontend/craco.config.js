const webpack = require("webpack")

module.exports = function () {
    const appTarget = process.env.REACT_APP_TEST_MODE ? "TestMode" : "Default"

    return {
        webpack: {
            plugins: [
                new webpack.NormalModuleReplacementPlugin(
                    /APP_TARGET-(\.*)/,
                    function (resource) {
                        resource.request = resource.request.replace(
                            /APP_TARGET-/,
                            `${appTarget}-`
                        )
                    }
                ),
            ],
        },
    }
}