"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";
import { ArrowRight, CheckCircle2, ChevronDown, ChevronUp, Lock, RefreshCw, Sparkles, X } from "lucide-react";

export type SetupStep = {
  key: string;
  title: string;
  detail: string;
  done: boolean;
  blocked_by: string | null;
  scope: string;
  link: string;
  optional?: boolean;
};

export type SetupState = {
  done: number;
  total: number;
  next: string | null;
  service_mode?: "execution" | "consulting" | string;
  steps: SetupStep[];
};

const DIRECT_V2_LINKS = new Set([
  "settings",
  "settings/connections",
  "settings/conversions",
  "settings/content",
  "settings/competitors",
  "settings/baseline",
  "settings/advanced",
  "settings/team",
  "watchlist",
  "engine",
  "llm",
  "site-health",
  "consulting",
  "consulting/recommendations",
  "consulting/report",
]);

export function resolveStepHref(
  slug: string,
  step: SetupStep,
  serviceMode: "execution" | "consulting" | string = "execution",
): string {
  const rawLink = (step.link ?? "").trim().replace(/^\/+/, "");
  if (DIRECT_V2_LINKS.has(rawLink)) {
    return `/${slug}/${rawLink}`;
  }

  switch (step.key) {
    case "account":
      return `/${slug}/settings`;
    case "sources":
    case "pull":
      return `/${slug}/settings/connections`;
    case "leads":
      return `/${slug}/settings/conversions`;
    case "baseline":
      return `/${slug}/settings/baseline`;
    case "competitors":
      return `/${slug}/settings/competitors`;
    case "watchlist":
      return `/${slug}/watchlist`;
    case "llm":
      return `/${slug}/llm`;
    case "site_health":
      return `/${slug}/site-health`;
    case "consulting_profile":
    case "consulting":
      return `/${slug}/consulting`;
    case "consulting_deliverable":
      return `/${slug}/consulting/recommendations`;
    case "first_run":
      return serviceMode === "consulting" ? `/${slug}/consulting` : `/${slug}/engine`;
    default:
      return `/${slug}/settings`;
  }
}

function dismissStorageKey(clientId: string): string {
  return `oiq-setup-dismissed-${clientId}`;
}

export function SetupHeaderPill({ slug, setup }: { slug: string; setup: SetupState }) {
  const complete = setup.total > 0 && setup.done >= setup.total;
  const pct = setup.total > 0 ? Math.round((setup.done / setup.total) * 100) : 0;

  return (
    <Link
      href={`/${slug}/settings`}
      className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold transition-colors ${
        complete
          ? "border-green-200 bg-green-50 text-green-800 hover:bg-green-100"
          : "border-[var(--border)] bg-[var(--surface)] text-[var(--text-primary)] hover:border-[var(--brand-teal)]"
      }`}
      title="View guided setup checklist"
    >
      <span
        className={`h-2 w-2 rounded-full ${complete ? "bg-green-600" : "bg-[var(--brand-teal)]"}`}
        aria-hidden="true"
      />
      <span className="tabular-nums">
        {complete ? `Setup complete · ${setup.done}/${setup.total}` : `Setup ${setup.done}/${setup.total} (${pct}%)`}
      </span>
    </Link>
  );
}

export function SetupBanner({
  clientId,
  slug,
  setup,
  serviceMode = "execution",
}: {
  clientId: string;
  slug: string;
  setup: SetupState;
  serviceMode?: "execution" | "consulting" | string;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [dismissed, setDismissed] = useState(false);
  const prevPathnameRef = useRef(pathname);

  useEffect(() => {
    try {
      setDismissed(window.localStorage.getItem(dismissStorageKey(clientId)) === "1");
    } catch {
      // Ignore storage failures
    }
  }, [clientId]);

  useEffect(() => {
    if (prevPathnameRef.current !== pathname) {
      prevPathnameRef.current = pathname;
      startTransition(() => {
        router.refresh();
      });
    }
  }, [pathname, router]);

  // Full checklist is shown directly on /[slug]/settings.
  if (pathname === `/${slug}/settings`) {
    return null;
  }

  const resolvedMode = setup.service_mode ?? serviceMode;
  const complete = setup.total > 0 && setup.done >= setup.total;
  const pct = setup.total > 0 ? Math.round((setup.done / setup.total) * 100) : 0;
  const requiredSteps = setup.steps.filter((s) => !s.optional);
  const optionalSteps = setup.steps.filter((s) => s.optional);
  const nextStep = setup.next ? requiredSteps.find((s) => s.key === setup.next) ?? null : null;

  if (complete) {
    if (dismissed) return null;
    return (
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-green-200 bg-green-50/70 px-4 py-2.5 text-xs text-green-900">
        <div className="flex items-center gap-2">
          <CheckCircle2 className="h-4 w-4 text-green-700" aria-hidden="true" />
          <span className="font-semibold">
            Guided setup complete ({setup.done}/{setup.total})
          </span>
          <Link href={`/${slug}/settings`} className="font-semibold text-[var(--brand-teal)] hover:underline">
            Review checklist
          </Link>
        </div>
        <button
          type="button"
          onClick={() => {
            setDismissed(true);
            try {
              window.localStorage.setItem(dismissStorageKey(clientId), "1");
            } catch {
              // Ignore storage failures
            }
          }}
          className="inline-flex items-center gap-1 rounded px-2 py-1 text-green-800 hover:bg-green-100"
          aria-label="Dismiss completed setup banner"
        >
          <X className="h-3.5 w-3.5" />
          <span>Dismiss</span>
        </button>
      </div>
    );
  }

  const nextHref = nextStep ? resolveStepHref(slug, nextStep, resolvedMode) : `/${slug}/settings`;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-1.5">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold text-[var(--text-primary)] tabular-nums">
              Guided setup: {setup.done} of {setup.total} complete
            </span>
            {resolvedMode === "consulting" ? (
              <span className="rounded-full bg-[var(--brand-teal-soft)] px-2 py-0.5 text-[11px] font-semibold text-[var(--brand-dark)]">
                Consulting
              </span>
            ) : null}
            <span className="text-[var(--text-tertiary)]">·</span>
            {nextStep ? (
              <span className="truncate text-[var(--text-secondary)]">
                Next: <strong className="text-[var(--text-primary)]">{nextStep.title}</strong> ({nextStep.detail})
              </span>
            ) : (
              <span className="text-[var(--text-secondary)]">Remaining steps are waiting on data syncs</span>
            )}
          </div>
          <div
            className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--background)]"
            role="progressbar"
            aria-valuenow={setup.done}
            aria-valuemin={0}
            aria-valuemax={setup.total}
          >
            <div
              className="h-full rounded-full bg-[var(--brand-teal)] transition-all duration-300"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() =>
              startTransition(() => {
                router.refresh();
              })
            }
            disabled={pending}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--background)] disabled:opacity-60"
            title="Refresh setup status"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${pending ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <Link
            href={`/${slug}/settings`}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--background)]"
          >
            All steps
          </Link>
          {nextStep ? (
            <Link
              href={nextHref}
              className="inline-flex items-center gap-1 rounded-lg bg-[var(--brand-teal)] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[var(--brand-teal-hover)]"
            >
              <span>Continue</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          ) : null}
        </div>
      </div>
    </div>
  );
}

export function SetupChecklist({
  clientId,
  slug,
  clientName,
  serviceMode = "execution",
  setup,
}: {
  clientId: string;
  slug: string;
  clientName: string;
  serviceMode?: "execution" | "consulting" | string;
  setup: SetupState;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const resolvedMode = setup.service_mode ?? serviceMode;
  const complete = setup.total > 0 && setup.done >= setup.total;

  const [collapsed, setCollapsed] = useState(complete);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    try {
      setDismissed(window.localStorage.getItem(dismissStorageKey(clientId)) === "1");
    } catch {
      // Ignore storage failures
    }
  }, [clientId]);

  const pct = setup.total > 0 ? Math.round((setup.done / setup.total) * 100) : 0;
  const requiredSteps = setup.steps.filter((s) => !s.optional);
  const optionalSteps = setup.steps.filter((s) => s.optional);
  const nextStep = setup.next ? requiredSteps.find((s) => s.key === setup.next) ?? null : null;

  if (complete && dismissed) {
    return (
      <div className="flex items-center justify-between rounded-xl border border-green-200 bg-green-50/60 px-4 py-2.5 text-xs text-green-900">
        <span className="inline-flex items-center gap-2 font-medium">
          <CheckCircle2 className="h-4 w-4 text-green-700" aria-hidden="true" />
          Guided setup complete ({setup.done}/{setup.total}) for {clientName}
        </span>
        <button
          type="button"
          onClick={() => {
            setDismissed(false);
            setCollapsed(false);
            try {
              window.localStorage.removeItem(dismissStorageKey(clientId));
            } catch {
              // Ignore storage failures
            }
          }}
          className="font-semibold text-[var(--brand-teal)] hover:underline"
        >
          View checklist
        </button>
      </div>
    );
  }

  return (
    <section
      id="guided-setup"
      aria-label="Guided setup checklist"
      className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 space-y-5"
    >
      {/* Header + Progress */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-[var(--text-primary)]">Guided setup</h2>
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                resolvedMode === "consulting"
                  ? "bg-[var(--brand-teal-soft)] text-[var(--brand-dark)]"
                  : "bg-[var(--background)] text-[var(--text-secondary)]"
              }`}
            >
              {resolvedMode === "consulting" ? "Consulting mode" : "Execution mode"}
            </span>
          </div>
          <p className="text-xs text-[var(--text-secondary)]">
            {complete
              ? `All ${setup.total} onboarding steps verified for ${clientName}.`
              : `${setup.done} of ${setup.total} steps complete for ${clientName}. Steps unlock in dependency order.`}
          </p>
          {resolvedMode === "consulting" ? (
            <p className="text-xs text-[var(--text-secondary)]">
              Consulting setup tracks connections, conversions, baseline, and advisory workspace readiness.
            </p>
          ) : null}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() =>
              startTransition(() => {
                router.refresh();
              })
            }
            disabled={pending}
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--background)] disabled:opacity-60"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${pending ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </button>
          <button
            type="button"
            onClick={() => setCollapsed((v) => !v)}
            className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--background)]"
          >
            {collapsed ? (
              <>
                <ChevronDown className="h-3.5 w-3.5" />
                <span>Show steps</span>
              </>
            ) : (
              <>
                <ChevronUp className="h-3.5 w-3.5" />
                <span>Hide steps</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="font-semibold text-[var(--text-primary)] tabular-nums">
            {setup.done} of {setup.total} steps complete
          </span>
          <span className="font-semibold text-[var(--text-secondary)] tabular-nums">{pct}%</span>
        </div>
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-[var(--background)]"
          role="progressbar"
          aria-valuenow={setup.done}
          aria-valuemin={0}
          aria-valuemax={setup.total}
        >
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              complete ? "bg-green-600" : "bg-[var(--brand-teal)]"
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Completed Banner */}
      {complete ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-green-200 bg-green-50/70 px-4 py-3 text-xs text-green-900">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="h-4 w-4 shrink-0 text-green-700" aria-hidden="true" />
            <span className="font-semibold">Setup complete — all {setup.total} steps verified.</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setCollapsed((v) => !v)}
              className="font-semibold text-[var(--brand-teal)] hover:underline"
            >
              {collapsed ? "Show checklist" : "Collapse checklist"}
            </button>
            <button
              type="button"
              onClick={() => {
                setDismissed(true);
                try {
                  window.localStorage.setItem(dismissStorageKey(clientId), "1");
                } catch {
                  // Ignore storage failures
                }
              }}
              className="rounded px-2 py-1 font-medium text-green-800 hover:bg-green-100"
            >
              Dismiss
            </button>
          </div>
        </div>
      ) : null}

      {/* Next Actionable Step Spotlight */}
      {!complete && nextStep ? (
        <div className="flex flex-wrap items-center justify-between gap-4 rounded-lg border border-[var(--brand-teal)]/40 bg-[var(--brand-teal-soft)]/25 p-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-[var(--brand-teal-hover)]">
              <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
              <span>Next step</span>
            </div>
            <div className="text-sm font-semibold text-[var(--text-primary)]">{nextStep.title}</div>
            <div className="text-xs text-[var(--text-secondary)]">{nextStep.detail}</div>
          </div>
          <Link
            href={resolveStepHref(slug, nextStep, resolvedMode)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--brand-teal-hover)]"
          >
            <span>Open {nextStep.title}</span>
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      ) : null}

      {/* Step-by-step List */}
      {!collapsed ? (
        <div className="space-y-4">
          <ol className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {requiredSteps.map((step, index) => {
              const href = resolveStepHref(slug, step, resolvedMode);
              const isNext = !step.done && !step.blocked_by && step.key === setup.next;
              const isBlocked = !step.done && Boolean(step.blocked_by);

              return (
                <li
                  key={step.key}
                  className={`flex flex-wrap items-center justify-between gap-4 px-4 py-3.5 ${
                    isNext ? "bg-[var(--brand-teal-soft)]/10" : ""
                  }`}
                >
                  <div className="flex min-w-0 flex-1 items-start gap-3">
                    {step.done ? (
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-green-100 text-green-700">
                        <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                      </span>
                    ) : isBlocked ? (
                      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-[var(--background)] text-[var(--text-tertiary)]">
                        <Lock className="h-3.5 w-3.5" aria-hidden="true" />
                      </span>
                    ) : (
                      <span
                        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold tabular-nums ${
                          isNext
                            ? "bg-[var(--brand-teal)] text-white"
                            : "border border-[var(--brand-teal)] text-[var(--brand-teal)]"
                        }`}
                      >
                        {index + 1}
                      </span>
                    )}

                    <div className="min-w-0 flex-1 space-y-0.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`text-sm font-semibold ${
                            isBlocked ? "text-[var(--text-secondary)]" : "text-[var(--text-primary)]"
                          }`}
                        >
                          {step.title}
                        </span>
                        {step.done ? (
                          <span className="rounded-full bg-green-100 px-2 py-0.5 text-[11px] font-semibold text-green-800">
                            Done
                          </span>
                        ) : isNext ? (
                          <span className="rounded-full bg-[var(--brand-teal-soft)] px-2 py-0.5 text-[11px] font-semibold text-[var(--brand-dark)]">
                            Up next
                          </span>
                        ) : isBlocked ? (
                          <span className="rounded-full bg-[var(--background)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)]">
                            Waiting
                          </span>
                        ) : (
                          <span className="rounded-full border border-[var(--border)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-secondary)]">
                            Ready
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-[var(--text-secondary)]">{step.detail}</p>
                      {isBlocked && step.blocked_by ? (
                        <p className="text-xs font-medium text-amber-800">Needs: {step.blocked_by}</p>
                      ) : null}
                    </div>
                  </div>

                  <div className="shrink-0">
                    {step.done ? (
                      <Link
                        href={href}
                        className="text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                      >
                        Review
                      </Link>
                    ) : isNext ? (
                      <Link
                        href={href}
                        className="inline-flex items-center gap-1 rounded-lg bg-[var(--brand-teal)] px-3 py-1.5 text-xs font-semibold text-white hover:bg-[var(--brand-teal-hover)]"
                      >
                        <span>Set up</span>
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    ) : isBlocked ? (
                      <Link
                        href={href}
                        className="text-xs font-medium text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] hover:underline"
                      >
                        View
                      </Link>
                    ) : (
                      <Link
                        href={href}
                        className="inline-flex items-center gap-1 rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--background)]"
                      >
                        <span>Open</span>
                        <ArrowRight className="h-3.5 w-3.5" />
                      </Link>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>

          {optionalSteps.length > 0 ? (
            <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--background)]/50 px-4 py-3 space-y-2">
              <div className="text-[11px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
                Optional enrichment (does not affect setup completion)
              </div>
              <ul className="divide-y divide-[var(--border)]">
                {optionalSteps.map((step) => {
                  const href = resolveStepHref(slug, step, resolvedMode);
                  return (
                    <li key={step.key} className="flex flex-wrap items-center justify-between gap-3 py-2 first:pt-1 last:pb-0">
                      <div className="min-w-0 flex-1 space-y-0.5">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-xs font-semibold text-[var(--text-primary)]">{step.title}</span>
                          <span className="rounded-full border border-[var(--border)] bg-[var(--surface)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
                            Optional
                          </span>
                          {step.done ? (
                            <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-800">
                              Added
                            </span>
                          ) : null}
                        </div>
                        <p className="text-xs text-[var(--text-secondary)]">{step.detail}</p>
                      </div>
                      <Link
                        href={href}
                        className="shrink-0 text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                      >
                        {step.done ? "Review" : "Add"}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
