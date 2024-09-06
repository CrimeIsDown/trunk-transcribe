const path = require('path')

/** @type {import('next').NextConfig} */
module.exports = {
  output: "standalone",
  sassOptions: {
    includePaths: [path.join(__dirname, "styles")],
  },
}
