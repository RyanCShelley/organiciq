import Link from "next/link";

import { clientHref } from "@/lib/client-path";

export type SetupStep = {
  key: string;
  title: string;
  detail: string;
  done: boolean;
  blocked_by: string | null;
  link: string;
};

export type SetupState = {
  done: number;
  total: number;
  next: string | null;
  steps: SetupStep[];
};

/**
 * What is set up for this client, and what to do next.
 *
 * The order is the dependency order rather than a preference: the lead
 * definitions screen reads GA4's own event names, so it has nothing to show
 * before the first pull; the baseline averages GA4 sessions and lead events,
 * so it needs both. Every row is measured on load, so a step cannot claim to
 * be done after somebody deletes the thing that made it so.
 *
 * Exactly one row is marked as next — the first that is neither done nor
 * blocked. A blocked row is never the next action; the thing blocking it is.
 */
export function SetupChecklist({
  state,
  clientSlug,
}: {
  state: SetupState;
  clientSlug: string;
}) {
  const complete = state.done === state.total;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-[13px] text-[var(--text-secondary)]">
          {complete ? (
            <span className="font-semibold text-[#15784F]">
              All {state.total} steps done — this client is ready to run.
            </span>
          ) : (
            <>
              <span className="font-semibold text-[var(--text-primary)]">
                {state.done} of {state.total} done
              </span>
              . Each step waits on the one it names.
            </>
          )}
        </p>
      </div>

      <ol className="mt-3">
        {state.steps.map((step, index) => {
          const isNext = step.key === state.next;
          return (
            <li
              key={step.key}
              className={`flex flex-wrap items-baseline gap-x-3 gap-y-1 border-t border-[var(--border)] py-2.5 ${
                isNext ? "bg-[#FFF8EE]" : ""
              }`}
            >
              <span
                aria-hidden
                className={`w-5 shrink-0 text-center text-[13px] font-semibold ${
                  step.done
                    ? "text-[#15784F]"
                    : isNext
                      ? "text-[#8A4B08]"
                      : "text-[var(--text-tertiary)]"
                }`}
              >
                {step.done ? "✓" : isNext ? "→" : index + 1}
              </span>

              <span
                className={`min-w-[190px] text-[13.5px] ${
                  step.done
                    ? "text-[var(--text-secondary)]"
                    : "font-semibold text-[var(--text-primary)]"
                }`}
              >
                {step.title}
                <span className="sr-only">
                  {step.done
                    ? " — done"
                    : step.blocked_by
                      ? " — blocked"
                      : isNext
                        ? " — do this next"
                        : ""}
                </span>
              </span>

              <span className="min-w-0 flex-1 text-[12.5px] text-[var(--text-secondary)]">
                {/* What is blocking it beats a restatement of the title. */}
                {step.blocked_by && !step.done ? (
                  <span className="text-[var(--text-tertiary)]">
                    Blocked: {step.blocked_by}
                  </span>
                ) : (
                  step.detail
                )}
              </span>

              {!step.done && !step.blocked_by ? (
                <Link
                  href={clientHref(clientSlug, step.link)}
                  className="shrink-0 text-[12.5px] font-semibold text-[var(--brand-teal-hover)] underline"
                >
                  Open
                </Link>
              ) : null}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
