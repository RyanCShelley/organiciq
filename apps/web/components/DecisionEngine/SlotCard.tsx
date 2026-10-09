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
export function SlotCard({
  action,
  children,
}: {
  action: RecordAction;
  children?: React.ReactNode;
}) {
  return (
    <article className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5">
      <div className="flex flex-wrap justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1 basis-[420px]">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
              Slot {action.slot} · {action.id}
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
          <dd className="font-semibold">{formatDay(action.check_on)}</dd>
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

      {children ? (
        <div className="mt-4 border-t border-[var(--border)] pt-4">{children}</div>
      ) : null}
    </article>
  );
}

/** A slot the engine would not fill, and the reason it gave. */
export function EmptySlotCard({ slot, reason }: { slot: number; reason: string }) {
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
