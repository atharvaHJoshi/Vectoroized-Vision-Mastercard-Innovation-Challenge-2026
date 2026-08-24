/**
 * The dashboard talks to the Python backend on port 8000.
 *
 * Rewrites proxy /api/* through Next's dev server so the browser sees a single
 * origin and there is no CORS involved. Override the backend location with
 * SG_API_URL if you run it elsewhere.
 */
const API = process.env.SG_API_URL || "http://127.0.0.1:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
};

module.exports = nextConfig;
