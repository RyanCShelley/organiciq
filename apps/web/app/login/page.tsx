import { signIn } from "@/lib/auth";

const HOSTED_DOMAIN = "smamarketing.net";

function errorMessage(error?: string): string {
  switch (error) {
    case "AccessDenied":
      return `Sign-in was denied. Use an @${HOSTED_DOMAIN} Google Workspace account (not a personal Gmail).`;
    case "Configuration":
      return "Sign-in configuration error. Try again from http://127.0.0.1:3000 (not localhost), or refresh and retry once.";
    case "OAuthCallback":
    case "Callback":
      return "Google callback failed (often a localhost vs 127.0.0.1 mismatch). Open http://127.0.0.1:3000/login and try again.";
    case "SessionExpired":
      return "Your session expired. Sign in again to continue.";
    default:
      return error
        ? `Sign-in failed (${error}). Use an @${HOSTED_DOMAIN} account and open http://127.0.0.1:3000`
        : "";
  }
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; callbackUrl?: string }>;
}) {
  const params = await searchParams;
  const message = errorMessage(params.error);

  return (
    <main className="flex min-h-screen items-center justify-center p-6">
      <div className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--card)] p-8 shadow-xl">
        <p className="text-sm uppercase tracking-[0.2em] text-[var(--muted)]">SMA Marketing</p>
        <h1 className="mt-2 text-3xl font-semibold">Organic IQ</h1>
        <p className="mt-3 text-sm text-[var(--muted)]">
          Sign in with your @{HOSTED_DOMAIN} Google Workspace account to continue.
        </p>

        {message ? (
          <p className="mt-4 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {message}
          </p>
        ) : null}

        <form
          className="mt-6"
          action={async () => {
            "use server";
            await signIn("google", { redirectTo: params.callbackUrl || "/dashboard" });
          }}
        >
          <button
            type="submit"
            className="w-full rounded-xl bg-[var(--accent)] px-4 py-3 text-sm font-medium text-white hover:opacity-90"
          >
            Continue with Google
          </button>
        </form>
      </div>
    </main>
  );
}
