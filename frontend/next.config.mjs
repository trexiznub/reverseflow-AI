/** @type {import('next').NextConfig} */
// PAGES_BASE_PATH is set only by the GitHub Pages workflow. It turns the app
// into a static export served from https://<user>.github.io/<repo>/.
const base = process.env.PAGES_BASE_PATH || "";

// BACKEND_URL makes the Next.js server forward /api/* to the backend, so the
// browser only talks to the website's own address. Used in SAP Business
// Application Studio, where the browser cannot reach the dev space's localhost.
// Pair it with NEXT_PUBLIC_API_URL="" so the app calls /api on the same origin.
const backend = process.env.BACKEND_URL || "";

const nextConfig = {
  reactStrictMode: true,
  ...(base
    ? { output: "export", basePath: base, trailingSlash: true, images: { unoptimized: true } }
    : {}),
  ...(!base && backend
    ? { async rewrites() { return [{ source: "/api/:path*", destination: `${backend.replace(/\/$/, "")}/api/:path*` }]; } }
    : {}),
};
export default nextConfig;
