import {
  BRANCH_LABEL,
  CONSTRAINT_LABEL,
  monthsHeld,
  passLine,
  testValue,
  type BranchResult,
  type BranchTest,
  type MonthlyRecord,
} from "@/lib/monthly-record";

const STATUS_CHIP: Record<string, string> = {
  pass: "bg-[#E5F4EC] text-[#15784F]",
  // A branch under its bar is where the month's work goes, not an alarm.
  fail: "bg-[#FDF1E3] text-[#8A4B08]",
  blocked: "bg-[#EEF1F3] text-[#3E4954]",
};

const STATUS_LABEL: Record<string, string> = {
  pass: "On track",
  fail: "Opportunity",
  blocked: "Blocked",
};

const CONFIDENCE_CHIP: Record<string, string> = {
  high: "bg-[#E5F4EC] text-[#15784F]",
  medium: "bg-[#FDF1E3] text-[#8A4B08]",
  low: "bg-[#FDF1E3] text-[#8A4B08]",
};

function headline(branch: BranchResult): BranchTest | undefined {
  return (
    branch.tests.find((t) => t.id === branch.headline_test) ?? branch.tests[0]
  );
}

/**
 * One tile per branch, carrying the metric's own name.
 *
 * The old tile said "43% of 30% bar" — a ratio with no metric attached, which
 * tells a reader nothing about what was measured. Each tile now names the
 * test, shows its value in its own unit, and states the bar in words.
 */
function BranchTile({
  branch,
  isConstraint,
}: {
  branch: BranchResult;
  isConstraint: boolean;
}) {
  const test = headline(branch);
  const failing = branch.status === "fail";
  const focus = isConstraint && failing;
  return (
    <div
      className={`rounded-[10px] border px-4 py-3.5 ${
        focus
          ? "border-2 border-[#0F8F82] bg-[#EEF9F7]"
          : "border-[var(--border)]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13.5px] font-semibold text-[var(--text-primary)]">
          {BRANCH_LABEL[branch.branch] ?? branch.branch}
        </span>
        <span
          className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold ${
            focus ? "bg-[#0F8F82] text-white" : STATUS_CHIP[branch.status]
          }`}
        >
          {focus
            ? "Focus"
            : (STATUS_LABEL[branch.status] ?? branch.status)}
        </span>
      </div>

      {branch.status === "blocked" ? (
        // A blocked tile says what is missing. "Blocked" on its own asks the
        // reader to go and find out why.
        <p className="mt-2 text-[12.5px] leading-snug text-[var(--text-secondary)]">
          {branch.missing?.[0] ?? test?.missing ?? "not enough data to judge"}
        </p>
      ) : (
        <>
          <p
            className={`mt-1.5 font-[family-name:var(--font-display)] text-[24px] font-black tabular-nums leading-none ${
              focus
                ? "text-[#0B6F65]"
                : failing
                  ? "text-[#8A4B08]"
                  : "text-[var(--text-primary)]"
            }`}
          >
            {test ? testValue(test) : "—"}
          </p>
          <p className="mt-1.5 text-[12px] leading-snug text-[var(--text-tertiary)]">
            {test ? `${test.metric_label} · ${passLine(test)}` : ""}
          </p>
        </>
      )}
    </div>
  );
}

export type SlotProgress = {
  /** Slots the plan allows. */
  total: number;
  /** Slots the engine filled with an action. */
  filled: number;
  /** Of those, how many somebody owns. */
  assigned: number;
  skipped: number;
};

/**
 * One pip per slot the plan allows, so the month reads at a glance.
 *
 * Three states and no more: taken on, set aside, and nobody has touched it.
 * An empty slot — one the engine could not fill — is drawn hollow rather
 * than hidden, because "we only found three things worth doing" is part of
 * what the month looks like.
 */
function SlotPips({ progress }: { progress: SlotProgress }) {
  const { total, filled, assigned, skipped } = progress;
  const untouched = Math.max(0, filled - assigned - skipped);
  const empty = Math.max(0, total - filled);
  const pips = [
    ...Array(assigned).fill("assigned"),
    ...Array(skipped).fill("skipped"),
    ...Array(untouched).fill("open"),
    ...Array(empty).fill("none"),
  ];
  const style: Record<string, string> = {
    assigned: "bg-[#15784F]",
    skipped: "bg-[var(--border-strong,#C9D1D8)]",
    open: "bg-[#F3D9B5]",
    none: "border border-dashed border-[var(--border-strong,#C9D1D8)]",
  };

  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-1" aria-hidden>
        {pips.map((kind, index) => (
          <span
            key={index}
            className={`h-2.5 w-5 rounded-full ${style[kind]}`}
          />
        ))}
      </div>
      <span className="text-[13px] text-[var(--text-secondary)]">
        <span className="font-semibold text-[var(--text-primary)]">
          {assigned} of {total}
        </span>{" "}
        assigned
        {skipped ? `, ${skipped} skipped` : ""}
        {empty ? `, ${empty} unfilled` : ""}
      </span>
    </div>
  );
}

/**
 * What this month is about, why, and whether to trust it.
 *
 * Answers the reader's three questions in order: which constraint, can I
 * trust it, and what do I do. The third is the slot cards below.
 */
export function ConstraintCard({
  record,
  progress,
}: {
  record: MonthlyRecord;
  progress?: SlotProgress;
}) {
  const label = CONSTRAINT_LABEL[record.constraint] ?? record.constraint;
  const held = monthsHeld(record.held_since, record.month);
  const overridden = record.override === "manual";
  // Counted off the card it points at, not off `confidence_reasons`: the
  // two lists overlap but are not the same length, and a chip saying "2
  // gaps below" above a card listing three is worse than no chip.
  const gaps = record.data_gaps?.length ?? 0;

  return (
    <section
      className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)] p-6"
      aria-labelledby="constraint-heading"
    >
      <div className="flex flex-wrap justify-between gap-5">
        <div className="min-w-0 flex-1 basis-[420px]">
          <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            This month&rsquo;s constraint
          </p>
          <h2
            id="constraint-heading"
            className="mt-1.5 font-[family-name:var(--font-display)] text-[30px] font-black leading-tight tracking-[-0.015em] text-[var(--text-primary)]"
          >
            {label}
          </h2>
          <p className="mt-2 max-w-[62ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
            {record.reason_text}
          </p>

          {/* An override is a disagreement, and the disagreement is the
              interesting part — so what the engine said stays visible beside
              what a person chose. */}
          {overridden && record.engine_constraint ? (
            <p className="mt-2 max-w-[62ch] rounded-[8px] bg-[var(--surface-muted)] px-3 py-2 text-[13px] leading-relaxed text-[var(--text-secondary)]">
              Overridden. The tests chose{" "}
              <span className="font-semibold text-[var(--text-primary)]">
                {CONSTRAINT_LABEL[record.engine_constraint] ?? record.engine_constraint}
              </span>
              ; the branch statuses below are still what they measured.
            </p>
          ) : null}
          {record.override === "relaunch_180d" ? (
            <p className="mt-2 text-[13px] text-[var(--text-secondary)]">
              Forced by a relaunch in the last 180 days.
            </p>
          ) : null}
        </div>

        <dl className="grid shrink-0 grid-cols-[auto_auto] content-start gap-x-5 gap-y-2 text-[13px]">
          <dt className="text-[var(--text-tertiary)]">Plan</dt>
          <dd className="font-semibold">
            {/* Only the plan name capitalises. `capitalize` on the whole
                line gave "Enterprise · 5 Slots". */}
            <span className="capitalize">{record.plan}</span> ·{" "}
            {record.action_slots} {record.action_slots === 1 ? "slot" : "slots"}
          </dd>
          {progress ? (
            <>
              <dt className="text-[var(--text-tertiary)]">Slots</dt>
              <dd>
                <SlotPips progress={progress} />
              </dd>
            </>
          ) : null}
          <dt className="text-[var(--text-tertiary)]">Held since</dt>
          <dd className="font-semibold">
            {record.held_since} (month {held})
          </dd>
          <dt className="text-[var(--text-tertiary)]">Confidence</dt>
          <dd>
            <span
              className={`inline-block rounded-full px-2.5 py-0.5 text-[12px] font-semibold ${
                CONFIDENCE_CHIP[record.confidence]
              }`}
            >
              {record.confidence[0].toUpperCase() + record.confidence.slice(1)}
              {gaps ? ` · ${gaps} gap${gaps === 1 ? "" : "s"} below` : ""}
            </span>
          </dd>
        </dl>
      </div>

      {/* The list that stood here was "Data that limited this run", printed
          a second time: both are built from the same blocked inputs, so one
          was always a strict subset of the other. The chip above still says
          how many there are, and that card says what they are. */}

      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        {record.branches.map((branch) => (
          <BranchTile
            key={branch.branch}
            branch={branch}
            isConstraint={branch.branch === record.constraint}
          />
        ))}
      </div>
    </section>
  );
}
