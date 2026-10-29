import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { LoginHostGuard } from "@/components/auth/LoginHostGuard";
import { LogoWordmark } from "@/components/brand/Logo";
import { BRAND } from "@/lib/brand";

const LOGIN_ORIGIN = "http://127.0.0.1:3001";

function errorMessage(error?: string): string {
  switch (error) {
    case "AccessDenied":
      return `Sign-in was denied. Use an @${BRAND.hostedDomain} Google Workspace account (not a personal Gmail).`;
    case "Configuration":
    case "OAuthCallback":
    case "Callback":
      return `Google rejected the sign-in redirect. Add ${LOGIN_ORIGIN}/api/auth/callback/google as an authorized redirect URI on the OAuth client, then try again.`;
    case "SessionExpired":
      return "Your session expired. Sign in again to continue.";
    default:
      return error ? `Sign-in failed (${error}). Open ${LOGIN_ORIGIN}/login and try again.` : "";
  }
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; callbackUrl?: string }>;
}) {
  const params = await searchParams;
  const callback =
    params.callbackUrl && params.callbackUrl.startsWith("/") && !params.callbackUrl.startsWith("//")
      ? params.callbackUrl
      : "/";
  const message = errorMessage(params.error);

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <LoginHostGuard />
      <div className="w-full max-w-sm rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-8 shadow-sm">
        <LogoWordmark className="text-2xl" />
        <p className="mt-1 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-tertiary)]">
          v2 · {BRAND.companyName}
        </p>
        <h1 className="mt-6 font-[family-name:var(--font-display)] text-xl font-bold">Sign in</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Use your @{BRAND.hostedDomain} Google account.
        </p>
        {message ? (
          <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">
            {message}
          </p>
        ) : null}
        <div className="mt-6">
          <GoogleSignInButton callbackUrl={callback} />
        </div>
      </div>
    </main>
  );
}
