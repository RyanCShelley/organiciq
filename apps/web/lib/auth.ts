import NextAuth from "next-auth";
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
    const res = await fetch(`${apiUrl}/auth/upsert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
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

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Allow both 127.0.0.1 and localhost during local dev.
  // Both redirect URIs must be registered in Google Cloud OAuth client.
  trustHost: true,
  providers: [
    Google({
      clientId: process.env.AUTH_GOOGLE_ID,
      clientSecret: process.env.AUTH_GOOGLE_SECRET,
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
});
