import NextAuth from "next-auth";
import type { NextAuthConfig } from "next-auth";
import Google from "next-auth/providers/google";
import { SignJWT, jwtVerify } from "jose";
import type { Session } from "next-auth";

/** SMA Workspace login domain — keep in sync with login page copy. */
const HOSTED_DOMAIN = "smamarketing.net";
const ACCESS_TOKEN_TTL = "7d";
const ACCESS_TOKEN_REFRESH_SKEW_SEC = 5 * 60;

function isSmaWorkspaceAccount(email: string, hd?: string | null): boolean {
  const normalized = email.trim().toLowerCase();
  if (normalized.endsWith(`@${HOSTED_DOMAIN}`)) return true;
  if ((hd ?? "").toLowerCase() === HOSTED_DOMAIN) return true;
  return false;
}

async function accessTokenNeedsRefresh(token?: string): Promise<boolean> {
  if (!token) return true;
  const secret = process.env.AUTH_SECRET;
  if (!secret) return true;

  try {
    const { payload } = await jwtVerify(token, new TextEncoder().encode(secret));
    const exp = payload.exp;
    if (!exp) return true;
    const now = Math.floor(Date.now() / 1000);
    return exp - now <= ACCESS_TOKEN_REFRESH_SKEW_SEC;
  } catch {
    return true;
  }
}

async function mintApiToken(input: {
  email: string;
  name: string | null;
  googleSub: string;
}): Promise<string | undefined> {
  const apiUrl = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  const secret = process.env.AUTH_SECRET;
  if (!secret || !input.email) return undefined;

  try {
    // Shared secret gating the upsert: it mints staff users, so the API must
    // only accept it from this app. Required in production on both sides.
    const internalSecret = process.env.INTERNAL_API_SECRET;
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
      console.warn("[auth] upsert failed", res.status, await res.text());
    }
  } catch (err) {
    console.warn("[auth] upsert unreachable", err);
  }

  const key = new TextEncoder().encode(secret);
  return new SignJWT({
    email: input.email.toLowerCase(),
    name: input.name,
    sub: input.googleSub,
  })
    .setProtectedHeader({ alg: "HS256" })
    .setIssuedAt()
    .setExpirationTime(ACCESS_TOKEN_TTL)
    .sign(key);
}

export async function ensureApiAccessToken(session: Session | null): Promise<string | undefined> {
  const email = session?.user?.email?.toLowerCase();
  if (!email) return undefined;

  const existing = session?.accessToken;
  if (existing && !(await accessTokenNeedsRefresh(existing))) {
    return existing;
  }

  return mintApiToken({
    email,
    name: session?.user?.name ?? null,
    googleSub: session?.googleSub || email,
  });
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
          hd: HOSTED_DOMAIN,
          prompt: "select_account",
          access_type: "online",
        },
      },
    }),
  ],
  session: {
    strategy: "jwt",
    // Keep SMA staff signed in; jwt callback still refreshes the API access token.
    maxAge: 30 * 24 * 60 * 60,
    // Re-run jwt callback periodically so stale API tokens get refreshed in the cookie.
    updateAge: 5 * 60,
  },
  callbacks: {
    async signIn({ user, profile, account }) {
      if (account?.provider !== "google") return false;

      const email = (user?.email || profile?.email || "").toLowerCase();
      const hd = (profile as { hd?: string } | undefined)?.hd;

      if (!isSmaWorkspaceAccount(email, hd)) {
        console.warn("[auth] denied non-SMA account", { email, hd });
        return false;
      }

      return true;
    },
    async jwt({ token, account, profile, user }) {
      const email = (profile?.email || user?.email || token.email || "").toLowerCase();
      const name = profile?.name || user?.name || token.name || null;
      const googleSub =
        profile?.sub || account?.providerAccountId || (token.sub as string | undefined) || email;

      if (account && email) {
        token.email = email;
        token.name = name;
        token.sub = googleSub;
      }

      if (
        email &&
        (await accessTokenNeedsRefresh(token.accessToken as string | undefined))
      ) {
        token.accessToken = await mintApiToken({
          email,
          name: name as string | null,
          googleSub,
        });
      }

      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string | undefined;
      session.googleSub = token.sub as string | undefined;
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
