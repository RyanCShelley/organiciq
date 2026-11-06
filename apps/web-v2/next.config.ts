import type { NextConfig } from "next";

// A full Content-Security-Policy is deliberately not set here: Next injects
// inline scripts, so a policy needs per-request nonces and a browser test of
// every page. `frame-ancestors` is the part that stops the app being framed
// and clicked through, and it needs neither.
const securityHeaders = [
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  // Next 16 blocks the dev server's scripts and hot reload when the page is opened at 127.0.0.1 (the address sign-in is set up for).
  allowedDevOrigins: ["127.0.0.1"],
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
};

export default nextConfig;
