const path = require("path");
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

module.exports = {
  entry: "./static/js/index.js",
  output: {
    filename: "bundle.js",
    path: path.resolve(__dirname, "static/dist"),
  },
  module: {
    rules: [
      {
        test: /\.js$/,
        exclude: /node_modules/,
        use: {
          loader: "babel-loader",
          options: {
            presets: ["@babel/preset-env"],
          },
        },
      },
      {
        test: /\.css$/,
        use: [MiniCssExtractPlugin.loader, "css-loader", "postcss-loader"],
      },
    ],
  },
  plugins: [
    new MiniCssExtractPlugin({
      filename: "styles.css",
    }),
  ],
  devServer: {
    contentBase: path.join(__dirname, "static/dist"),
    compress: true,
    port: 8080,
    writeToDisk: true,
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "static/js"),
    },
  },
  watch: true,
  watchOptions: {
    ignored: /node_modules/,
    poll: 1000 // Check for changes every second
  }
};