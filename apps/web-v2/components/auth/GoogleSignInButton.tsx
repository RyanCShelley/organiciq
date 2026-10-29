"use client";

import { useState } from "react";
import { signIn } from "next-auth/react";

/**
 * Client sign-in hits `/api/auth/signin/google` so Auth.js applies AUTH_URL
 * the same way on authorize and token exchange. Server-action signIn can
 * skip that rewrite and send a different redirect_uri (localhost vs 127.0.0.1).
 */
export function GoogleSignInButton({ callbackUrl }: { callbackUrl: string }) {
  const [pending, setPending] = useState(false);

  return (
    <button
      type="button"
      className="btn btn-primary w-full py-3"
      disabled={pending}
      onClick={async () => {
        setPending(true);
        try {
          await signIn("google", { callbackUrl, redirect: true });
        } catch {
          setPending(false);
        }
      }}
    >
      {pending ? "Redirecting to Google…" : "Continue with Google"}
    </button>
  );
}
