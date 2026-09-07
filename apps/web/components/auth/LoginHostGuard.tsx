"use client";

import { useEffect } from "react";

/**
 * Prefer 127.0.0.1 over localhost for Google OAuth. Chrome and Auth.js treat
 * them as different sites; AUTH_URL is pinned to 127.0.0.1.
 */
export function LoginHostGuard() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.hostname !== "localhost") return;

    const next = new URL(window.location.href);
    next.hostname = "127.0.0.1";
    window.location.replace(next.toString());
  }, []);

  return null;
}
