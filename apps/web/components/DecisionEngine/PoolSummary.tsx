import type { RecordAction } from "@/lib/monthly-record";

type State = "planned" | "assigned" | "done" | "skipped";

/**
 * Each marker is one slot. Colour says what the team has done with it, and
 * an empty slot is hollow, so "what is filled and what isn't" reads before
 * any number does. Two colours carry meaning (somebody owns it / nobody
 * has yet) for the same reason the cards do.
 */
const PIP: Record<State | "empty", string> = {
  planned: "border-[var(--brand-teal-deep,#0F6B6B)] bg-[#E3F1F1] text-[#0F5252]",
  assigned: "border-[#15784F] bg-[#15784F] text-white",
  done: "border-[#15784F] bg-[#15784F] text-white",
  skipped: "border-[var(--border-strong,#C9D1D8)] bg-[#EEF1F3] text-[#6B7681] line-through",
  empty: "border-dashed border-[var(--border-strong,#C9D1D8)] bg-transparent text-[var(--text-tertiary)]",
};

const PIP_LABEL: Record<State | "empty", string> = {
  planned: "In the plan, not assigned",
  assigned: "Assigned",
  done: "Done",
  skipped: "Skipped",
  empty: "Empty",
};

function path(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

function Stat({
  label,
  value,
  of,
  note,
}: {
  label: string;
  value: number;
  of?: number;
  note?: string;
}) {
  return (
    <div className="min-w-[150px] flex-1">
      <p className="text-[11.5px] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1 font-[family-name:var(--font-display)] text-[28px] font-extrabold leading-none tabular-nums text-[var(--text-primary)]">
        {value.toLocaleString()}
        {of !== undefined ? (
          <span className="ml-1 text-[16px] font-bold text-[var(--text-tertiary)]">
            of {of.toLocaleString()}
          </span>
        ) : null}
      </p>
      {note ? (
        <p className="mt-1.5 text-[12.5px] leading-snug text-[var(--text-secondary)]">{note}</p>
      ) : null}
    </div>
  );
}

/**
 * The top of a retainer pool: how much the engine found, how much of the
 * allowance it filled, and where each slot stands.
 *
 * Every number is counted off the lists the page renders, so the strip can
 * never disagree with the cards below it.
 */
export function PoolSummary({
  filled,
  slots,
  weighed,
  statusOf,
  anchorPrefix,
  noun,
}: {
  /** Slotted actions, in slot order. */
  filled: RecordAction[];
  /** The allowance for the month. */
  slots: number;
  /** Everything the engine weighed, slotted or not. */
  weighed: number;
  statusOf: (uid: string) => State | undefined;
  anchorPrefix: string;
  noun: string;
}) {
  const waiting = Math.max(0, weighed - filled.length);
  const empty = Math.max(0, slots - filled.length);
  const count = (s: State) => filled.filter((a) => (statusOf(a.action_uid) ?? "planned") === s).length;
  const assigned = count("assigned");
  const done = count("done");
  const skipped = count("skipped");
  const unowned = filled.length - assigned - done - skipped;

  const markers: { key: string; state: State | "empty"; slot: number; title: string }[] = [];
  for (let n = 1; n <= slots; n++) {
    const action = filled.find((a) => a.slot === n);
    markers.push(
      action
        ? {
            key: action.action_uid,
            state: statusOf(action.action_uid) ?? "planned",
            slot: n,
            title: path(action.target_url) || action.title,
          }
        : { key: `empty-${n}`, state: "empty", slot: n, title: "Nothing qualified for this slot" },
    );
  }

  return (
    <div
      className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] px-6 py-5"
      aria-label={`${noun} plan summary`}
    >
      <div className="flex flex-wrap gap-x-8 gap-y-5">
        <Stat
          label="Pages available"
          value={weighed}
          note={
            weighed === 0
              ? `Nothing qualified for a ${noun}.`
              : waiting > 0
                ? `${filled.length} in the plan, ${waiting} waiting below`
                : "All of them are in the plan"
          }
        />
        <Stat
          label="Slots filled"
          value={filled.length}
          of={slots}
          note={
            slots === 0
              ? "No slots this month"
              : empty > 0
                ? `${empty} empty — nothing else qualified`
                : waiting > 0
                  ? "Full. The rest wait for next month"
                  : "Full"
          }
        />
        <Stat
          label="Handed off"
          value={assigned + done}
          of={filled.length}
          note={
            filled.length === 0
              ? undefined
              : `${unowned} still unassigned${skipped ? ` · ${skipped} skipped` : ""}${done ? ` · ${done} done` : ""}`
          }
        />
      </div>

      {slots > 0 ? (
        <div className="mt-5 border-t border-[var(--border)] pt-4">
          <ol className="flex flex-wrap gap-2" aria-label="Slots">
            {markers.map((m) => {
              const cls = `flex h-9 min-w-9 items-center justify-center rounded-[8px] border px-2 font-[family-name:var(--font-mono)] text-[12.5px] font-semibold ${PIP[m.state]}`;
              const label = `Slot ${m.slot}: ${PIP_LABEL[m.state]} — ${m.title}`;
              return (
                <li key={m.key}>
                  {m.state === "empty" ? (
                    <span className={cls} title={label} aria-label={label}>
                      {m.slot}
                    </span>
                  ) : (
                    <a
                      href={`#${anchorPrefix}-${m.slot}`}
                      className={`${cls} hover:brightness-95`}
                      title={label}
                      aria-label={label}
                    >
                      {m.slot}
                    </a>
                  )}
                </li>
              );
            })}
          </ol>
          <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[12px] text-[var(--text-tertiary)]">
            {(["planned", "assigned", "skipped", "empty"] as const).map((s) => (
              <li key={s} className="flex items-center gap-1.5">
                <span
                  aria-hidden="true"
                  className={`inline-block h-3 w-3 rounded-[3px] border ${PIP[s].split(" ").filter((c) => !c.startsWith("text-") && c !== "line-through").join(" ")}`}
                />
                {PIP_LABEL[s]}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
