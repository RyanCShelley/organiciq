import { BRANCH_LABEL, formatDay, type RecordAction } from "@/lib/monthly-record";

const BRANCH_CHIP: Record<string, string> = {
  visibility: "bg-[#E9EEF8] text-[#2C4A86]",
  traffic: "bg-[#EEF1F3] text-[#3E4954]",
  leads: "bg-[#FBE9E2] text-[#8E3414]",
};

const FLAG_LABEL: Record<string, string> = {
  small_sample: "Small sample",
  fallback_used: "Fallback used",
  no_target_mapping: "No target mapping",
};

function path(url: string): string {
  // A new-page action has no URL yet; its identity is the term.
  if (!url) return "New page";
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

/**
 * One slot: what to do, where, why, and how anyone will know it is done.
 *
 * The old row led with the problem and repeated the full URL twice. This
 * leads with the instruction, states the path once, and carries the three
 * things that decide whether an action can be handed to somebody: how long
 * it takes, what it is measured on, and when it gets checked.
 */
/**
 * The card's edge carries the state, so a plan can be read at arm's length.
 *
 * Only two things are worth colouring: somebody owns it, and nobody is doing
 * it. A separate colour for sent and shipped would make five states compete
 * for the same glance and tell you less than the chip beside the buttons
 * already does.
 */
const EDGE: Record<string, string> = {
  assigned: "border-l-[3px] border-l-[#15784F] bg-[#FAFDFB]",
  done: "border-l-[3px] border-l-[#15784F] bg-[#FAFDFB]",
  skipped: "border-l-[3px] border-l-[var(--border-strong,#C9D1D8)] opacity-70",
};

const STATE_CHIP: Record<string, { label: string; className: string }> = {
  assigned: { label: "Assigned", className: "bg-[#E5F4EC] text-[#15784F]" },
  done: { label: "Done", className: "bg-[#E5F4EC] text-[#15784F]" },
  skipped: { label: "Skipped", className: "bg-[#EEF1F3] text-[#3E4954]" },
};

export function SlotCard({
  action,
  status,
  yours,
  children,
}: {
  action: RecordAction;
  /** Put in the plan by a person; the engine had left it out. */
  yours?: boolean;
  /** What the team has done about it: planned, assigned, done or skipped. */
  status?: string;
  children?: React.ReactNode;
}) {
  const chip = status ? STATE_CHIP[status] : undefined;
  return (
    <article
      className={`rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5 ${
        (status && EDGE[status]) || ""
      }`}
    >
      <div className="flex flex-wrap justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-[420px]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
              {action.family ? action.steps && action.steps.length > 1 ? `Delivery brief ${action.slot} · ${action.steps.length} actions` : `Action ${action.slot}` : `Slot ${action.slot}`}{yours ? " · your pick" : ""}
            </span>
            <span
              className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold ${
                BRANCH_CHIP[action.branch] ?? BRANCH_CHIP.traffic
              }`}
            >
              {BRANCH_LABEL[action.branch] ?? action.branch}
            </span>
            {/* Spillover means the constraint ran out of work, which is a
                different thing from this being the constraint's work. */}
            {action.spillover ? (
              <span className="rounded-full bg-[#FDF1E3] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#8A4B08]">
                Spillover
              </span>
            ) : null}
            {chip ? (
              <span
                className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold ${chip.className}`}
              >
                {chip.label}
              </span>
            ) : null}
            {(action.flags ?? []).map((flag) => (
              <span
                key={flag}
                className="rounded-full bg-[#FDF1E3] px-2.5 py-0.5 text-[11.5px] font-semibold text-[#8A4B08]"
              >
                {FLAG_LABEL[flag] ?? flag}
              </span>
            ))}
          </div>

          <h3 className="mt-1.5 font-[family-name:var(--font-display)] text-[17px] font-extrabold leading-snug text-[var(--text-primary)]">
            {action.title}
          </h3>
          <p className="mt-1 break-words font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-secondary)]">
            {path(action.target_url)}
          </p>
        </div>

        <dl className="grid shrink-0 grid-cols-[auto_auto] content-start gap-x-4 gap-y-1 text-[13px]">
          <dt className="text-[var(--text-tertiary)]">Effort</dt>
          <dd className="font-semibold">{action.effort_min} min</dd>
          <dt className="text-[var(--text-tertiary)]">Measured by</dt>
          <dd className="font-semibold">{action.metric}</dd>
          <dt className="text-[var(--text-tertiary)]">Check on</dt>
          <dd className="font-semibold">{action.check_after_days ? `${action.check_after_days} days after shipment` : formatDay(action.check_on)}</dd>
        </dl>
      </div>

      <div className="mt-4 grid gap-x-6 gap-y-3 text-[13px] sm:grid-cols-2">
        <div>
          <p className="font-semibold text-[var(--text-primary)]">Why this page</p>
          <p className="mt-1 leading-relaxed text-[var(--text-secondary)]">
            {action.why}
          </p>
        </div>
        <div>
          <p className="font-semibold text-[var(--text-primary)]">Done when</p>
          <p className="mt-1 leading-relaxed text-[var(--text-secondary)]">
            {action.done_when}
          </p>
        </div>
      </div>

      {/* The job, in order. Every line is built from something found on
          this page, so a brief is a checklist rather than an instruction
          to go and work out what is wrong. */}
      {action.steps && action.steps.length > 0 ? (
        <div className="mt-4">
          <p className="text-[13px] font-semibold text-[var(--text-primary)]">
            Steps
          </p>
          <ol className="mt-2 space-y-1.5">
            {action.steps.map((step, index) => (
              <li
                key={step}
                className="flex gap-2.5 text-[13px] leading-relaxed text-[var(--text-secondary)]"
              >
                <span
                  aria-hidden
                  className="mt-[2px] flex h-[18px] w-[18px] flex-none items-center justify-center rounded-full bg-[var(--surface-muted)] text-[10.5px] font-bold text-[var(--text-tertiary)]"
                >
                  {index + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      {action.evidence?.length ? <details className="mt-4 text-sm"><summary className="cursor-pointer font-semibold">Evidence and limitations</summary><ul className="mt-2 list-disc space-y-1 pl-5">{action.evidence.map((line, index) => <li key={index}>{line}</li>)}</ul></details> : null}
      {children ? (
        <div className="mt-4 border-t border-[var(--border)] pt-4">{children}</div>
      ) : null}
    </article>
  );
}

/** A slot the engine would not fill, and the reason it gave. */
export function EmptySlotCard({ slot, reason }: { slot: number | string; reason: string }) {
  return (
    <article className="rounded-[var(--radius-lg,14px)] border border-dashed border-[var(--border)] px-6 py-5">
      <p className="font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
        Slot {slot}
      </p>
      <p className="mt-1 font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-secondary)]">
        Empty slot
      </p>
      <p className="mt-1 max-w-[70ch] text-[13px] leading-relaxed text-[var(--text-tertiary)]">
        {reason}
      </p>
    </article>
  );
}
