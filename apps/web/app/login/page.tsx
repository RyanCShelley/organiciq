import { GoogleSignInButton } from "@/components/auth/GoogleSignInButton";
import { LoginHostGuard } from "@/components/auth/LoginHostGuard";
import { LogoWordmark } from "@/components/brand/Logo";
import { BRAND } from "@/lib/brand";

const LOGIN_ORIGIN = "http://127.0.0.1:3000";
const GOOGLE_CALLBACK = `${LOGIN_ORIGIN}/api/auth/callback/google`;
const LOCALHOST_CALLBACK = "http://localhost:3000/api/auth/callback/google";

function errorMessage(error?: string): string {
  switch (error) {
    case "AccessDenied":
      return `Sign-in was denied. Use an @${BRAND.hostedDomain} Google Workspace account (not a personal Gmail).`;
    case "Configuration":
    case "OAuthCallback":
    case "Callback":
      return [
        "Google rejected the OAuth redirect URI (redirect_uri_mismatch).",
        `In Google Cloud → Credentials → the OAuth client for AUTH_GOOGLE_ID, add Authorized redirect URI: ${GOOGLE_CALLBACK}`,
        `Also add ${LOCALHOST_CALLBACK} if you ever open localhost.`,
        `Keep the data OAuth URI if this client is shared: http://127.0.0.1:8000/oauth/google/callback`,
        `Then open ${LOGIN_ORIGIN}/login and try Continue with Google again.`,
      ].join(" ");
    case "SessionExpired":
      return "Your session expired. Sign in again to continue.";
    default:
      return error
        ? `Sign-in failed (${error}). Use an @${BRAND.hostedDomain} account and open ${LOGIN_ORIGIN}/login`
        : "";
  }
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; callbackUrl?: string }>;
}) {
  const params = await searchParams;
  const safeCallback =
    params.callbackUrl && params.callbackUrl.startsWith("/") && !params.callbackUrl.startsWith("//")
      ? params.callbackUrl
      : "/dashboard";
  const message = errorMessage(params.error);

  return (
    <main className="min-h-screen md:grid md:grid-cols-[1.1fr_0.9fr]">
      <LoginHostGuard />
      <section className="brand-panel relative flex min-h-[16rem] flex-col justify-between overflow-hidden px-8 py-10 md:min-h-screen md:p-12">
        <div className="relative z-10">
          <LogoWordmark inverse className="text-2xl md:text-[1.75rem]" />
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-[var(--base)]">
            {BRAND.companyName}
          </p>
        </div>
        <div className="relative z-10 mt-10 max-w-lg md:mt-0">
          <p className="badge badge-accent mb-4 w-fit">{BRAND.productName}</p>
          <h1 className="font-[family-name:var(--font-display)] text-4xl font-bold leading-[1.05] tracking-tight text-[var(--base-2)] md:text-5xl">
            Predictable organic growth, powered by validated data.
          </h1>
          <p className="mt-5 text-base leading-relaxed text-[var(--base)] md:text-lg">
            {BRAND.companyName}&apos;s internal operating system for diagnosis, prioritization,
            and client delivery.
          </p>
        </div>
      </section>

      <section className="flex items-center justify-center bg-[var(--background)] p-6 sm:p-10">
        <div className="card-elevated w-full max-w-md p-8">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted)]">
            {BRAND.companyName}
          </p>
          <h2 className="mt-2 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">
            Sign in to {BRAND.productName}
          </h2>
          <p className="mt-3 text-[var(--muted)]">
            Use your @{BRAND.hostedDomain} Google Workspace account to continue.
          </p>
          <p className="mt-2 text-xs text-[var(--muted)]">
            Local login URL:{" "}
            <a className="underline" href={`${LOGIN_ORIGIN}/login`}>
              {LOGIN_ORIGIN}/login
            </a>
          </p>

          {message ? <div className="alert alert-danger mt-4 text-sm leading-relaxed">{message}</div> : null}

          <div className="mt-6">
            <GoogleSignInButton callbackUrl={safeCallback} />
          </div>
        </div>
      </section>
    </main>
  );
}
