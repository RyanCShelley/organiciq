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
  fail: "bg-[#B4441C] text-white",
  blocked: "bg-[#EEF1F3] text-[#3E4954]",
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
  return (
    <div
      className={`rounded-[10px] border px-4 py-3.5 ${
        isConstraint && failing
          ? "border-2 border-[#B4441C] bg-[#FDF4F0]"
          : "border-[var(--border)]"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13.5px] font-semibold text-[var(--text-primary)]">
          {BRANCH_LABEL[branch.branch] ?? branch.branch}
        </span>
        <span
          className={`whitespace-nowrap rounded-full px-2.5 py-0.5 text-[11.5px] font-semibold ${
            STATUS_CHIP[branch.status]
          }`}
        >
          {branch.status === "fail" && isConstraint
            ? "Fail · constraint"
            : branch.status[0].toUpperCase() + branch.status.slice(1)}
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
              failing ? "text-[#8E3414]" : "text-[var(--text-primary)]"
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

/**
 * What this month is about, why, and whether to trust it.
 *
 * Answers the reader's three questions in order: which constraint, can I
 * trust it, and what do I do. The third is the slot cards below.
 */
export function ConstraintCard({ record }: { record: MonthlyRecord }) {
  const label = CONSTRAINT_LABEL[record.constraint] ?? record.constraint;
  const held = monthsHeld(record.held_since, record.month);
  const overridden = record.override === "manual";
  const checks = record.confidence_reasons ?? [];

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
              {checks.length
                ? ` · check ${checks.length} thing${checks.length === 1 ? "" : "s"}`
                : ""}
            </span>
          </dd>
        </dl>
      </div>

      {/* Low confidence with no list is an accusation without an address. */}
      {checks.length > 0 ? (
        <div
          role="note"
          className="mt-5 rounded-[10px] border border-[#F3D9B5] bg-[#FFF8EE] px-4 py-3.5"
        >
          <p className="text-[13px] font-semibold text-[#6B3A06]">
            Check before you assign
          </p>
          <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            {checks.map((check) => (
              <li key={check.code + check.text}>{check.text}</li>
            ))}
          </ol>
        </div>
      ) : null}

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
