import NextAuth from "next-auth";
import type { NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import { SignJWT } from "jose";
import type { Session } from "next-auth";

import { HOSTED_DOMAINS, isSmaWorkspaceAccount } from "@/lib/workspace-account";

// A short-lived credential, signed on the server for each request and never
// stored in the session. It used to live in the session for seven days, which
// the browser could read from /api/auth/session: anything running on the page
// (an extension, a future XSS) could lift a week-long key to the whole API.
const ACCESS_TOKEN_TTL = "15m";

/**
 * Create or refresh the user in the API. Called once, at sign-in.
 *
 * Fails closed: if the user cannot be registered, nobody is signed in. It used
 * to log a warning and mint a token anyway, so a misconfigured deploy
 * authenticated people without the shared-secret gate that exists to stop that.
 */
async function registerUser(input: {
  email: string;
  name: string | null;
  googleSub: string;
}): Promise<boolean> {
  const apiUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  const internalSecret = process.env.INTERNAL_API_SECRET;
  if (!internalSecret && process.env.NODE_ENV === "production") {
    console.error("[auth] INTERNAL_API_SECRET is not set; refusing sign-in");
    return false;
  }
  try {
    const res = await fetch(`${apiUrl}/auth/upsert`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(internalSecret ? { "X-OrganicIQ-Internal-Secret": internalSecret } : {}),
      },
      body: JSON.stringify({
        email: input.email,
        name: input.name,
        google_sub: input.googleSub,
      }),
    });
    if (!res.ok) {
      // Status only: the body and the address can name a real person.
      console.warn("[auth] sign-in refused by the API", res.status);
    }
    return res.ok;
  } catch {
    console.warn("[auth] the API was unreachable at sign-in");
    return false;
  }
}

async function signApiToken(email: string, name: string | null): Promise<string | undefined> {
  const secret = process.env.AUTH_SECRET;
  if (!secret || !email) return undefined;
  return new SignJWT({ email: email.toLowerCase(), name, sub: email.toLowerCase() })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(ACCESS_TOKEN_TTL)
    .sign(new TextEncoder().encode(secret));
}

/** The bearer token for one server-side call, signed now from the verified session. */
export async function ensureApiAccessToken(session: Session | null): Promise<string | undefined> {
  const email = session?.user?.email?.toLowerCase();
  if (!email) return undefined;
  return signApiToken(email, session?.user?.name ?? null);
}

/**
 * Canonical local origin for Google OAuth.
 * Next.js rewrites `127.0.0.1` → `localhost` on NextRequest, so Auth.js route
 * handlers must use a plain Request with this origin or authorize/token
 * redirect_uri values diverge (Google: redirect_uri_mismatch).
 */
export const AUTH_ORIGIN =
  (process.env.AUTH_URL || process.env.NEXTAUTH_URL || "http://127.0.0.1:3000").replace(
    /\/$/,
    "",
  );

process.env.AUTH_URL ||= AUTH_ORIGIN;
process.env.NEXTAUTH_URL ||= AUTH_ORIGIN;

export const authConfig = {
  // Local Google OAuth must stay on 127.0.0.1. Chrome treats localhost as a
  // different site, which breaks cookies on callback.
  trustHost: true,
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
      // Confidential web client: state is enough. PKCE cookies were being
      // consumed by middleware on the Google callback and failing in Chrome.
      checks: ["state"],
      authorization: {
        params: {
          // `hd` takes a single domain and would lock out the other one, so it
          // is only sent when there is exactly one. The signIn callback is the
          // actual boundary either way; this is just the account-chooser hint.
          ...(HOSTED_DOMAINS.length === 1 ? { hd: HOSTED_DOMAINS[0] } : {}),
          prompt: "select_account",
          access_type: "online",
        },
      },
    }),
  ],
  session: {
    strategy: "jwt",
    // A day, sliding with use. It was thirty days, so someone removed from the
    // Workspace stayed signed in for a month unless the API had been told to
    // deactivate them. Google sign-in is silent for anyone already signed in.
    maxAge: 24 * 60 * 60,
    updateAge: 60 * 60,
  },
  callbacks: {
    async signIn({ user, profile, account }) {
      if (account?.provider !== "google") return false;

      const email = (user?.email || profile?.email || "").toLowerCase();
      const claims = profile as { hd?: string; email_verified?: boolean; sub?: string } | undefined;

      // Google must say it checked the address belongs to this person.
      if (claims?.email_verified !== true) {
        console.warn("[auth] denied: email not verified by Google");
        return false;
      }
      if (!isSmaWorkspaceAccount(email, claims?.hd)) {
        // The domain and whether `hd` was present, never the address itself.
        console.warn("[auth] denied non-SMA account", {
          domain: email.split("@").pop(),
          hasHd: Boolean(claims?.hd),
        });
        return false;
      }

      return registerUser({
        email,
        name: (profile?.name || user?.name || null) as string | null,
        googleSub: claims?.sub || account?.providerAccountId || email,
      });
    },
    async jwt({ token, account, profile, user }) {
      if (account) {
        const email = (profile?.email || user?.email || token.email || "").toLowerCase();
        token.email = email;
        token.name = profile?.name || user?.name || token.name || null;
        token.sub = profile?.sub || account.providerAccountId || email;
      }
      return token;
    },
    async session({ session, token }) {
      // Identity only. Nothing here can authenticate a request: this object is
      // returned to the browser by /api/auth/session.
      if (session.user) {
        session.user.email = (token.email as string) ?? session.user.email;
        session.user.name = (token.name as string) ?? session.user.name;
      }
      return session;
    },
  },
  pages: {
    signIn: "/login",
    error: "/login",
  },
  secret: process.env.AUTH_SECRET,
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
