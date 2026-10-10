import Link from "next/link";

const CONSTRAINT_CHIP: Record<string, string> = {
  visibility: "bg-[#E9EEF8] text-[#2C4A86]",
  traffic: "bg-[#EEF1F3] text-[#3E4954]",
  leads: "bg-[#FBE9E2] text-[#8E3414]",
  visibility_expansion: "bg-[#E5F4EC] text-[#15784F]",
  withheld: "bg-[#FDF1E3] text-[#8A4B08]",
};

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

export type PortfolioClient = {
  client_id: string;
  slug: string;
  client: string;
  plan: string | null;
  constraint: string;
  constraint_label: string;
  visibility: string | null;
  traffic: string | null;
  leads: string | null;
  confidence: string;
  held_since: string;
  slots: number;
  filled: number;
  spillover: number;
  empty: number;
  data_gaps: string[];
  overridden: boolean;
};

export type Portfolio = {
  month: string | null;
  mixed_months: boolean;
  totals: {
    clients: number;
    run: number;
    withheld: number;
    capacity: number;
    filled: number;
    empty: number;
    spillover: number;
    leads_blocked: number;
    on_visibility: number;
  };
  by_constraint: { constraint: string; label: string; clients: number }[];
  data_gaps: { input: string; clients: number }[];
  clients: PortfolioClient[];
};

function monthName(month: string | null): string {
  if (!month) return "—";
  const [year, m] = month.split("-").map(Number);
  return new Date(Date.UTC(year, m - 1, 1)).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

function Tile({
  label,
  value,
  sub,
}: {
  label: string;
  value: number;
  sub: string;
}) {
  return (
    <div className="rounded-[10px] border border-[var(--border)] px-4 py-3.5">
      <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-1.5 font-[family-name:var(--font-display)] text-[26px] font-black tabular-nums leading-none text-[var(--text-primary)]">
        {value}
      </p>
      <p className="mt-1.5 text-[12px] leading-snug text-[var(--text-tertiary)]">
        {sub}
      </p>
    </div>
  );
}

/** A branch result, or an em dash where the record carries no status. */
function StatusCell({ status }: { status: string | null }) {
  if (!status) return <span className="text-[var(--text-tertiary)]">—</span>;
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${
        STATUS_CHIP[status] ?? STATUS_CHIP.blocked
      }`}
    >
      {status[0].toUpperCase() + status.slice(1)}
    </span>
  );
}

/**
 * Every client's month on one screen.
 *
 * Counted from the saved runs rather than recomputed, so a client's row here
 * and its own page cannot disagree. Ordered by the ladder — Visibility first,
 * Withheld last — because that is the order the work is decided in, and
 * within a constraint by how much of the plan is filled.
 */
export function PortfolioOverview({ data }: { data: Portfolio }) {
  const t = data.totals;
  const maxBar = Math.max(1, ...data.by_constraint.map((b) => b.clients));

  if (!t.clients) {
    return (
      <div className="workspace-panel">
        <p className="text-[14px] text-[var(--text-secondary)]">
          No client has a saved run yet. The portfolio counts saved runs rather
          than recomputing, so it fills in as each client&rsquo;s first run
          lands.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* The one sentence somebody reads before anything else. */}
      <p className="max-w-[80ch] text-[14.5px] leading-relaxed text-[var(--text-secondary)]">
        <span className="font-semibold text-[var(--text-primary)]">
          {monthName(data.month)}
          {data.mixed_months ? " and earlier" : ""}.
        </span>{" "}
        {t.on_visibility} of {t.clients}{" "}
        {t.clients === 1 ? "client is" : "clients are"} held on Visibility.{" "}
        {t.filled} of {t.capacity} plan action slots are filled
        {t.spillover
          ? `, ${t.spillover} of them by spillover to the next failing branch`
          : ""}
        .
      </p>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <Tile
          label="Clients run"
          value={t.run}
          sub={`${t.withheld} withheld for missing or stale data`}
        />
        <Tile
          label="Slots filled"
          value={t.filled}
          sub={`of ${t.capacity} allowed by plans`}
        />
        <Tile
          label="By spillover"
          value={t.spillover}
          sub="passed to the next failing branch"
        />
        <Tile
          label="Empty slots"
          value={t.empty}
          sub="no qualifying target in a failing branch"
        />
        <Tile
          label="Leads blocked"
          value={t.leads_blocked}
          sub="clients missing what the lead tests need"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="workspace-panel">
          <h2 className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]">
            Where each client is stuck
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            The month&rsquo;s one constraint: the first branch whose tests fail.
          </p>
          <ul className="mt-3 space-y-2">
            {data.by_constraint.map((row) => (
              <li key={row.constraint} className="flex items-center gap-3">
                <span className="w-[140px] shrink-0 text-[13px] text-[var(--text-secondary)]">
                  {row.label}
                </span>
                <span
                  className="h-[18px] rounded-[4px] bg-[var(--brand-teal-deep)]"
                  style={{
                    width: `${(row.clients / maxBar) * 100}%`,
                    minWidth: row.clients ? "6px" : "0",
                  }}
                  aria-hidden
                />
                <span className="text-[13px] font-semibold tabular-nums text-[var(--text-primary)]">
                  {row.clients}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="workspace-panel">
          <h2 className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]">
            What is missing most
          </h2>
          <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
            Inputs a rule needed and did not have, and how many clients each one
            costs. Worth fixing in this order.
          </p>
          {data.data_gaps.length === 0 ? (
            <p className="mt-3 text-[13px] text-[var(--text-tertiary)]">
              Nothing was missing in any client&rsquo;s run.
            </p>
          ) : (
            <ul className="mt-3 space-y-1.5">
              {data.data_gaps.slice(0, 8).map((gap) => (
                <li
                  key={gap.input}
                  className="flex items-baseline justify-between gap-3 border-t border-[var(--border)] pt-1.5 text-[13px]"
                >
                  <span className="min-w-0 flex-1 text-[var(--text-secondary)]">
                    {gap.input}
                  </span>
                  <span className="shrink-0 font-semibold tabular-nums">
                    {gap.clients}{" "}
                    <span className="font-normal text-[var(--text-tertiary)]">
                      {gap.clients === 1 ? "client" : "clients"}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <section className="workspace-panel">
        <h2 className="font-[family-name:var(--font-display)] text-[16px] font-extrabold text-[var(--text-primary)]">
          Clients
        </h2>
        <p className="mt-1 text-[13px] leading-relaxed text-[var(--text-secondary)]">
          Branch results run top down: Visibility, then Traffic, then Leads.
          Blocked means the branch is missing the data it needs.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-[11px] font-bold uppercase tracking-[0.1em] text-[var(--text-tertiary)]">
                <th className="py-2 pr-3 font-bold">Client</th>
                <th className="py-2 pr-3 font-bold">Plan</th>
                <th className="py-2 pr-3 font-bold">Constraint</th>
                <th className="py-2 pr-3 text-right font-bold">Slots</th>
                <th className="py-2 pr-3 font-bold">Visibility</th>
                <th className="py-2 pr-3 font-bold">Traffic</th>
                <th className="py-2 pr-3 font-bold">Leads</th>
                <th className="py-2 pr-3 font-bold">Confidence</th>
                <th className="py-2 font-bold">Held since</th>
              </tr>
            </thead>
            <tbody>
              {data.clients.map((row) => (
                <tr
                  key={row.client_id}
                  className="border-b border-[var(--border)] last:border-0"
                >
                  <td className="py-2 pr-3">
                    <Link
                      href={`/${row.slug}/decision-engine`}
                      className="font-semibold text-[var(--text-primary)] no-underline hover:underline"
                    >
                      {row.client}
                    </Link>
                  </td>
                  <td className="py-2 pr-3 capitalize text-[var(--text-secondary)]">
                    {row.plan ?? "—"}
                  </td>
                  <td className="py-2 pr-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${
                        CONSTRAINT_CHIP[row.constraint] ?? CONSTRAINT_CHIP.withheld
                      }`}
                    >
                      {row.constraint_label}
                    </span>
                    {/* An override is a disagreement, and worth seeing here. */}
                    {row.overridden ? (
                      <span className="ml-1.5 text-[11px] text-[var(--text-tertiary)]">
                        overridden
                      </span>
                    ) : null}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums text-[var(--text-secondary)]">
                    {row.filled}/{row.slots}
                  </td>
                  <td className="py-2 pr-3">
                    <StatusCell status={row.visibility} />
                  </td>
                  <td className="py-2 pr-3">
                    <StatusCell status={row.traffic} />
                  </td>
                  <td className="py-2 pr-3">
                    <StatusCell status={row.leads} />
                  </td>
                  <td className="py-2 pr-3">
                    <span
                      className={`inline-block rounded-full px-2 py-0.5 text-[11.5px] font-semibold ${
                        CONFIDENCE_CHIP[row.confidence] ?? CONFIDENCE_CHIP.low
                      }`}
                    >
                      {row.confidence[0].toUpperCase() + row.confidence.slice(1)}
                    </span>
                  </td>
                  <td className="py-2 tabular-nums text-[var(--text-secondary)]">
                    {row.held_since}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
