import { monthLabel } from "@/lib/focus";
import type { Scorecards as Data } from "@/lib/review";

const TONE = { up: "bg-[#e7fedc] text-[#2f6b0d]", down: "bg-[#fde8e4] text-[#b23a15]", flat: "bg-[#eceef2] text-[#4a5468]" } as const;
const WORD = { up: "Up", down: "Down", flat: "Flat" } as const;
const MIX = ["#00a99d", "#7fd6c9", "#223540", "#8a929d", "#cfd2d6"];

const num = (n: number | null | undefined) => (n == null ? "–" : Math.round(n).toLocaleString());
const move = (pct: number | null | undefined) => (pct == null ? "" : Math.abs(Math.round(pct)) < 1 ? "flat" : `${pct > 0 ? "up" : "down"} ${Math.abs(Math.round(pct))}%`);
const tone = (pct: number | null | undefined) => (pct == null || Math.abs(pct) < 5 ? "flat" : pct > 0 ? "up" : "down");

function Chip({ verdict, children }: { verdict: keyof typeof TONE; children: React.ReactNode }) {
  return <span className={`inline-block whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${TONE[verdict]}`}>{children}</span>;
}

function Row({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-[var(--border)] py-1.5 text-sm first:border-t-0">
      <span className="min-w-0 truncate text-[var(--text-secondary)]">{label}</span>
      <span className="shrink-0 font-semibold tabular-nums">{children}</span>
    </div>
  );
}

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <section aria-label={label} className="flex min-w-0 flex-col rounded-2xl border border-[var(--border)] bg-white p-5">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">{label}</h2>
      {children}
    </section>
  );
}

const Big = ({ children }: { children: React.ReactNode }) => <div className="mt-1 font-[family-name:var(--font-heading)] text-[2.1rem] font-bold leading-tight tracking-tight tabular-nums">{children}</div>;

/** One line that says the month, then Visibility, Traffic and Conversions as three cards of the same height. */
export function Scorecards({ data }: { data: Data }) {
  const v = data.visibility;
  const t = data.traffic;
  const c = data.conversions;
  const prior = monthLabel(data.previous_month).split(" ")[0];
  const total = t.channels.reduce((n, ch) => n + ch.sessions, 0);

  return (
    <section aria-label="The month at a glance" className="mb-6 space-y-4">
      {data.headline ? (
        <div className="rounded-2xl bg-[var(--brand-navy)] px-5 py-4 text-[0.95rem] leading-relaxed text-[#e8f6f3]">
          <p className="mb-1 text-[0.7rem] font-medium uppercase tracking-[0.06em] text-[#9db3bd]">{monthLabel(data.month).split(" ")[0]} in one line</p>
          {data.headline}
        </div>
      ) : null}

      <div className="grid gap-4 @3xl:grid-cols-3">
        <Card label="Visibility">
          {v.available ? (
            <>
              <Big>{num(v.headline)} of {num(v.of)}</Big>
              <div><Chip verdict={v.verdict}>{WORD[v.verdict]}</Chip> <span className="text-xs text-[var(--text-secondary)]">terms showing in Google</span></div>
              <div className="mt-3 flex-1">
                <Row label="Page one">{num(v.page_one)} {v.page_one === 1 ? "term" : "terms"}</Row>
                <Row label="AI mentions">{v.ai_mentions == null ? "–" : num(v.ai_mentions)}</Row>
                <Row label="AI links">{v.ai_links == null ? "–" : num(v.ai_links)}</Row>
                {v.has_bing ? <Row label="Bing">{num(v.bing)} of {num(v.of)} terms</Row> : null}
                <Row label="Google impressions">{num(v.impressions.current)}{v.impressions.change_pct != null ? <span className="font-normal text-[var(--text-secondary)]"> · {move(v.impressions.change_pct)}</span> : null}</Row>
              </div>
              {v.ai_runs && v.ai_runs > 1 ? <p className="mt-2 text-[0.7rem] text-[var(--text-tertiary)]">AI figures pool {v.ai_runs} runs this month.</p> : null}
            </>
          ) : (
            <p className="mt-3 text-sm text-[var(--text-secondary)]">No watchlist terms yet, so there is nothing to show here. Add some under Client settings.</p>
          )}
        </Card>

        <Card label="Traffic">
          <Big>{num(t.headline)}</Big>
          <div>
            {t.change_pct != null ? <Chip verdict={tone(t.change_pct)}>{move(t.change_pct).replace(/^./, (x) => x.toUpperCase())}</Chip> : null} <span className="text-xs text-[var(--text-secondary)]">sessions vs {prior}</span>
          </div>
          {total > 0 ? (
            <div className="mt-3 flex h-3 overflow-hidden rounded-full bg-[#eceef2]" role="img" aria-label="Where visits came from">
              {t.channels.map((ch, i) => <i key={ch.key} style={{ width: `${(ch.sessions / total) * 100}%`, background: MIX[i % MIX.length] }} />)}
            </div>
          ) : null}
          <div className="mt-2 flex-1">
            {t.channels.map((ch, i) => (
              <div key={ch.key} className="grid grid-cols-[0.75rem_1fr_auto_auto] items-center gap-2.5 border-t border-[var(--border)] py-1.5 text-sm first:border-t-0">
                <span className="h-2.5 w-2.5 rounded-[3px]" style={{ background: MIX[i % MIX.length] }} aria-hidden />
                <span className="truncate text-[var(--text-secondary)]">{ch.label}</span>
                <b className="font-semibold tabular-nums">{num(ch.sessions)}</b>
                <span className="w-14 text-right"><Chip verdict={tone(ch.change_pct)}>{ch.change_pct == null ? "new" : move(ch.change_pct).replace("up ", "+").replace("down ", "−").replace("flat", "0%")}</Chip></span>
              </div>
            ))}
            {t.channels.length === 0 ? <p className="text-sm text-[var(--text-secondary)]">No channel data for this month.</p> : null}
          </div>
        </Card>

        <Card label="Conversions">
          <Big>{num(c.headline)}</Big>
          <div>
            {c.change_pct != null ? <Chip verdict={tone(c.change_pct)}>{move(c.change_pct).replace(/^./, (x) => x.toUpperCase())}</Chip> : null}{" "}
            <span className="text-xs text-[var(--text-secondary)]">{c.previous != null ? `vs ${num(c.previous)} in ${prior}` : c.noun}</span>
          </div>
          {c.goal ? (
            <div className="mt-3">
              <div className="flex justify-between text-sm"><span className="text-[var(--text-secondary)]">Goal for the period</span><b className="font-semibold tabular-nums">{c.goal_progress_pct != null ? `${Math.round(c.goal_progress_pct)}% of ` : ""}{num(c.goal)}</b></div>
              <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-[#eceef2]"><i className="block h-full rounded-full bg-[#00a99d]" style={{ width: `${Math.min(100, c.goal_progress_pct ?? 0)}%` }} /></div>
            </div>
          ) : null}
          <div className="mt-3 flex-1">
            <p className="mb-0.5 text-[0.7rem] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Top conversions</p>
            {c.top.map((r) => (
              <Row key={r.label} label={r.label}>{num(r.count)}{r.change_pct != null ? <span className="font-normal text-[var(--text-secondary)]"> · {move(r.change_pct)}</span> : null}</Row>
            ))}
            {c.top.length === 0 ? <p className="py-1.5 text-sm text-[var(--text-secondary)]">No conversion events are set up for this client.</p> : null}
            {c.revenue && c.revenue.current != null ? <Row label="Revenue">{num(c.revenue.current)}{c.revenue.change_pct != null ? <span className="font-normal text-[var(--text-secondary)]"> · {move(c.revenue.change_pct)}</span> : null}</Row> : null}
          </div>
        </Card>
      </div>
    </section>
  );
}
