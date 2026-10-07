import type { NextConfig } from "next";

const BACKEND = process.env.NM_BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // The browser only ever talks to this web app; /api/* is forwarded to the local backend.
  // Same origin → no CORS, and the login cookie stays HttpOnly.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
