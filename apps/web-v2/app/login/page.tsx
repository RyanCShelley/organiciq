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
      return `Sign-in failed after Google. The web server's log has the reason (a wrong client secret, or ${LOGIN_ORIGIN}/api/auth/callback/google missing from the OAuth client's redirect URIs).`;
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
    <main className="min-h-screen md:grid md:grid-cols-[1.1fr_0.9fr]">
      <LoginHostGuard />
      <section className="relative flex min-h-[16rem] flex-col justify-center overflow-hidden bg-[var(--brand-dark-2)] px-8 py-10 text-[var(--background)] md:min-h-screen md:p-12">
        <div className="absolute left-8 top-10 z-10 md:left-12 md:top-12">
          <LogoWordmark inverse className="text-2xl md:text-[1.75rem]" />
          <p className="mt-3 text-xs font-semibold uppercase tracking-[0.18em] text-[#e8e8e8]">{BRAND.companyName}</p>
        </div>
        <div className="relative z-10 max-w-lg pt-20 md:pt-0">
          <p className="mb-4 w-fit rounded-full border border-[rgb(0_169_157/30%)] bg-[rgb(0_169_157/14%)] px-3 py-0.5 text-xs font-semibold text-[var(--brand-teal-soft)]">{BRAND.productName}</p>
          <h1 className="font-[family-name:var(--font-display)] text-4xl font-bold leading-[1.05] tracking-tight text-[var(--background)] md:text-5xl">
            Predictable organic growth, powered by validated data.
          </h1>
          <p className="mt-5 text-base leading-relaxed text-[#e8e8e8] md:text-lg">
            {BRAND.companyName}&apos;s internal operating system for diagnosis, prioritization, and client delivery.
          </p>
        </div>
      </section>

      <section className="flex items-center justify-center bg-[var(--background)] p-6 sm:p-10">
        <div className="w-full max-w-md rounded-xl border border-[#ececec] bg-[var(--surface)] p-8 shadow-sm">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--text-secondary)]">{BRAND.companyName}</p>
          <h2 className="mt-2 font-[family-name:var(--font-display)] text-3xl font-bold tracking-tight">Sign in to {BRAND.productName}</h2>
          <p className="mt-3 text-[var(--text-secondary)]">Use your @{BRAND.hostedDomain} Google Workspace account to continue.</p>
          {message ? (
            <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm leading-relaxed text-red-800">
              {message}
            </p>
          ) : null}
          <div className="mt-6">
            <GoogleSignInButton callbackUrl={callback} />
          </div>
        </div>
      </section>
    </main>
  );
}
