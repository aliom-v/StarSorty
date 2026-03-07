/** @type {import("next").NextConfig} */
const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
  experimental: {
    webpackBuildWorker: false,
  },
};

module.exports = nextConfig;
