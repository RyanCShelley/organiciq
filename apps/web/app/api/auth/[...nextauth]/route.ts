import { Auth } from "@auth/core";
import type { NextAuthConfig } from "next-auth";
import type { NextRequest } from "next/server";

import { AUTH_ORIGIN, authConfig } from "@/lib/auth";

/**
 * NextRequest normalizes 127.0.0.1 → localhost, which breaks Google OAuth when
 * AUTH_URL is 127.0.0.1. Pass a plain Request so Auth.js sees the canonical host
 * for both authorize and token exchange.
 */
function toCanonicalRequest(req: NextRequest): Request {
  const incoming = new URL(req.url);
  const canonical = new URL(AUTH_ORIGIN);
  incoming.protocol = canonical.protocol;
  incoming.hostname = canonical.hostname;
  incoming.port = canonical.port;

  const method = req.method.toUpperCase();
  const init: RequestInit = {
    method,
    headers: req.headers,
  };
  if (method !== "GET" && method !== "HEAD") {
    init.body = req.body;
    // Node fetch requires duplex when streaming a body.
    (init as RequestInit & { duplex: "half" }).duplex = "half";
  }
  return new Request(incoming.toString(), init);
}

export async function GET(req: NextRequest) {
  return Auth(toCanonicalRequest(req), authConfig as NextAuthConfig);
}

export async function POST(req: NextRequest) {
  return Auth(toCanonicalRequest(req), authConfig as NextAuthConfig);
}
