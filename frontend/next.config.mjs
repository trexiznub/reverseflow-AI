/** @type {import('next').NextConfig} */
// PAGES_BASE_PATH is set only by the GitHub Pages workflow. It turns the app
// into a static export served from https://<user>.github.io/<repo>/.
const base = process.env.PAGES_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  ...(base
    ? { output: "export", basePath: base, trailingSlash: true, images: { unoptimized: true } }
    : {}),
};
export default nextConfig;
