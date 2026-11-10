"use client";

import { Check, Eye, BarChart3, Target } from "lucide-react";
import { useState, type ReactNode } from "react";

import { monthLabel } from "@/lib/focus";
import type { Pair, Review, Scorecards } from "@/lib/review";

const TONE = { good: "bg-[#e7fedc] text-[#2f6b0d]", bad: "bg-[#fde8e4] text-[#b23a15]", flat: "bg-[#eceef2] text-[#4a5468]" } as const;
const MIX = ["#00a99d", "#7fd6c9", "#223540", "#8a929d", "#cfd2d6"];

export const num = (n: number | null | undefined, digits = 0) => (n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits }));
const money = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }));
const words = (pct: number) => `${pct > 0 ? "up" : "down"} ${Math.abs(Math.round(pct))}%`;

/** How a number moved, as a small coloured chip. Every measure here is better when higher. */
export function Change({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return null;
  if (Math.abs(pct) < 1) return <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${TONE.flat}`}>• flat</span>;
  return (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${pct > 0 ? TONE.good : TONE.bad}`}>
      {pct > 0 ? "▲" : "▼"} {words(pct)}
    </span>
  );
}

const Delta = ({ pct }: { pct: number | null | undefined }) =>
  pct == null || Math.abs(pct) < 1 ? null : <span className={`font-normal ${pct > 0 ? "text-[#2f6b0d]" : "text-[#b23a15]"}`}> · {pct > 0 ? "+" : "−"}{Math.abs(Math.round(pct))}%</span>;

export function Facts({ rows }: { rows: [string, ReactNode][] }) {
  return (
    <div className="mt-2 space-y-0.5 border-t border-[var(--border)] pt-2">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-3 text-[0.78rem] text-[var(--text-secondary)]">
          <span>{label}</span>
          <b className="text-right font-semibold tabular-nums text-[var(--text-primary)]">{value}</b>
        </div>
      ))}
    </div>
  );
}

export function Bar({ pct, className = "" }: { pct: number; className?: string }) {
  return (
    <div className={`my-2 h-1.5 overflow-hidden rounded-full bg-[#eceef2] ${className}`}>
      <i className="block h-full rounded-full bg-[#00a99d]" style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  );
}

/** One figure with what it counts and where it came from. The figure is modest in size so the words stay readable. */
export function StatCard({ label, source, value, unit, change, changeNote, bar, note, facts, children }: {
  label: string;
  source: string;
  value: ReactNode;
  unit?: string;
  change?: number | null;
  changeNote?: string;
  bar?: number;
  note?: ReactNode;
  facts?: [string, ReactNode][];
  children?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col rounded-2xl border border-[var(--border)] bg-white px-4 py-3.5">
      <div className="flex items-baseline justify-between gap-2 text-xs font-medium text-[var(--text-secondary)]">
        <span>{label}</span>
        <span className="text-[0.62rem] font-semibold uppercase tracking-wider text-[var(--text-tertiary)]">{source}</span>
      </div>
      <div className="mt-0.5 font-[family-name:var(--font-heading)] text-[1.75rem] font-bold leading-tight tracking-tight tabular-nums">
        {value}
        {unit ? <small className="ml-1 text-base font-semibold text-[var(--text-tertiary)]">{unit}</small> : null}
      </div>
      {change != null || changeNote ? (
        <div className="mt-0.5 flex flex-wrap items-center gap-2">
          <Change pct={change} />
          {changeNote ? <span className="text-xs text-[var(--text-secondary)]">{changeNote}</span> : null}
        </div>
      ) : null}
      {bar != null ? <Bar pct={bar} /> : null}
      {note ? <p className="text-xs leading-snug text-[var(--text-secondary)]">{note}</p> : null}
      {facts ? <Facts rows={facts} /> : null}
      {children}
    </div>
  );
}

const ICONS = { visibility: Eye, traffic: BarChart3, leads: Target } as const;

/** A section's title, one line on what its numbers say, and the button that makes it next month's focus. */
export function SectionHead({ kind, title, read, active = false, onFocus }: { kind: keyof typeof ICONS; title: string; read: string | null | undefined; active?: boolean; onFocus?: () => void }) {
  const Icon = ICONS[kind];
  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1">
      <Icon size={18} className="text-[var(--text-tertiary)]" aria-hidden />
      <h2 className="font-[family-name:var(--font-heading)] text-base font-bold">{title}</h2>
      {read ? <p className="min-w-[14rem] flex-1 text-sm text-[var(--text-secondary)]">{read}</p> : <span className="flex-1" />}
      {onFocus ? (
        <button
          type="button"
          onClick={onFocus}
          aria-pressed={active}
          className={`inline-flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold ${active ? "border-[var(--brand-navy)] bg-[var(--brand-navy)] text-white" : "border-[var(--border)] bg-white hover:bg-[var(--background)]"}`}
        >
          Focus here {active ? <Check size={12} aria-hidden /> : null}
        </button>
      ) : null}
    </div>
  );
}

/** The month in one line, with Copy for pasting the written summary into an email. */
export function Band({ data, lines }: { data: Scorecards; lines: string[] }) {
  const [copied, setCopied] = useState(false);
  if (!data.headline) return null;
  return (
    <div className="rounded-2xl bg-[var(--brand-navy)] px-5 py-4 text-[0.95rem] leading-relaxed text-[#e8f6f3]">
      <div className="mb-1 flex items-center justify-between gap-3">
        <p className="text-[0.7rem] font-medium uppercase tracking-[0.06em] text-[#9db3bd]">{monthLabel(data.month).split(" ")[0]} in one line</p>
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard.writeText(lines.join("\n"));
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="rounded-md border border-white/25 px-2 py-0.5 text-[0.7rem] font-semibold text-[#e8f6f3] hover:bg-white/10"
        >
          {copied ? "Copied" : "Copy full summary"}
        </button>
      </div>
      {data.headline}
    </div>
  );
}

const pctOf = (a: number | null | undefined, b: number | null | undefined) => (a != null && b ? (a / b) * 100 : 0);
const pair = (p: Pair | undefined | null) => p?.change_pct ?? null;

export function VisibilityCards({ review, cards }: { review: Review; cards: Scorecards }) {
  const v = cards.visibility;
  const vis = review.visibility;
  const rank = v.rank_check;
  const llm = vis?.llm;
  if (!v.available || !vis) {
    return <p className="rounded-xl border border-dashed border-[var(--border)] p-4 text-sm text-[var(--text-secondary)]">No watchlist terms yet, so there is nothing to show here. Add some under Client settings.</p>;
  }
  const rate = llm?.summary.visibility_rate;
  const pts = rate?.delta != null ? Math.round(rate.delta * 100) : null;
  const check = llm?.brand_check ?? [];
  const asked = check.reduce((n, b) => n + b.answers, 0);
  const cited = check.reduce((n, b) => n + b.site_cited, 0);
  const runWhen = llm ? (llm.in_month ? (v.ai_runs && v.ai_runs > 1 ? `${v.ai_runs} runs this month, pooled` : `run of ${llm.run_date}`) : `latest run ${llm.run_date}, after this month`) : "";
  return (
    <div className="space-y-3">
      <div className="grid gap-3 @3xl:grid-cols-3">
        <StatCard
          label="Google visibility"
          source="Search Console"
          value={num(v.headline)}
          unit={`of ${num(v.of)} terms`}
          change={v.impressions.change_pct}
          changeNote="impressions vs last month"
          bar={pctOf(v.headline, v.of)}
          note="Watchlist terms with at least one Google impression this month"
          facts={[
            ["Impressions", num(v.impressions.current)],
            ["Clicks from these terms", num(vis.summary.google_clicks)],
            ["On page one", `${num(v.page_one)} ${v.page_one === 1 ? "term" : "terms"}`],
          ]}
        />
        <StatCard
          label="Rank check"
          source="SE Ranking"
          value={rank ? num(rank.ranked) : "–"}
          unit={rank ? `of ${num(rank.tracked)} terms` : undefined}
          changeNote={rank ? `in Google's top 100 on ${new Date(`${rank.checked_on}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })}` : undefined}
          bar={rank ? pctOf(rank.ranked, rank.tracked) : undefined}
          note={rank ? "Daily check at a fixed location" : "No SE Ranking checks this month."}
          facts={
            rank
              ? [
                  ["In the top 10", num(rank.top10)],
                  ...(rank.best ? ([["Best", `${rank.best.keyword} · ${rank.best.position}`]] as [string, ReactNode][]) : []),
                  ...(rank.biggest_drop ? ([["Biggest drop", `${rank.biggest_drop.keyword} · ${rank.biggest_drop.from} → ${rank.biggest_drop.to}`]] as [string, ReactNode][]) : []),
                ]
              : undefined
          }
        />
        {v.has_bing ? (
          <StatCard
            label="Bing"
            source="Bing Webmaster"
            value={num(v.bing)}
            unit={`of ${num(v.of)} terms`}
            changeNote="Stands in for Microsoft Copilot"
            bar={pctOf(v.bing, v.of)}
            note="Terms with a Bing impression. Bing reports weekly; a week counts toward the month it starts in."
          />
        ) : null}
      </div>

      {llm ? (
        <div className="grid gap-3 @3xl:grid-cols-2">
          <StatCard
            label="AI discovery visibility"
            source="AI runs"
            value={rate ? `${Math.round(rate.current * 100)}%` : "–"}
            changeNote={pts == null ? undefined : pts === 0 ? "unchanged vs the run before" : `${pts > 0 ? "up" : "down"} ${Math.abs(pts)} ${Math.abs(pts) === 1 ? "point" : "points"} vs the run before`}
            note={`Share of AI answers to discovery prompts that named or cited the brand · ${runWhen}`}
            facts={[
              ["Mentions", num(llm.summary.mentions.current)],
              ["Citations", num(llm.summary.citations.current)],
            ]}
          />
          <StatCard
            label="AI brand links"
            source="AI runs"
            value={asked ? num(cited) : "–"}
            unit={asked ? `of ${num(asked)} answers` : undefined}
            bar={asked ? pctOf(cited, asked) : undefined}
            note={asked ? `Answers to prompts that name the brand where the AI linked to the site: ${check.map((b) => `${b.platform} ${b.site_cited}/${b.answers}`).join(", ")}` : "No answers to prompts that name the brand yet."}
          />
        </div>
      ) : null}

      {llm && llm.platforms.length > 0 ? (
        <div className="rounded-2xl bg-[var(--background)] px-4 py-3.5">
          <div className="mb-2 flex justify-between text-sm font-semibold">
            AI visibility by platform <span className="font-normal text-[var(--text-tertiary)]">Discovery prompts</span>
          </div>
          {llm.platforms.map((p) => (
            <div key={p.platform} className="grid grid-cols-[5.5rem_1fr_2.5rem] items-center gap-3 py-0.5 text-sm">
              <span>{p.platform}</span>
              <div className="h-1.5 overflow-hidden rounded-full bg-[#eceef2]"><i className="block h-full rounded-full bg-[#00a99d]" style={{ width: `${Math.round(p.visibility_rate.current * 100)}%` }} /></div>
              <em className="text-right not-italic tabular-nums text-[var(--text-secondary)]">{Math.round(p.visibility_rate.current * 100)}%</em>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function TrafficCards({ review, cards }: { review: Review; cards: Scorecards }) {
  const t = cards.traffic;
  const total = t.channels.reduce((n, c) => n + c.sessions, 0);
  const mix = Object.fromEntries(t.channels.map((c) => [c.key, c]));
  const others = t.channels.filter((c) => c.key !== "organic_search" && c.key !== "ai_referral");
  const prior = monthLabel(cards.previous_month).split(" ")[0];
  const organic = review.organic_sessions;
  return (
    <div className="grid gap-3 @3xl:grid-cols-3">
      <StatCard label="All sessions" source="GA4" value={num(t.headline)} change={t.change_pct} changeNote={t.previous != null ? `vs ${prior} · was ${num(t.previous)}` : undefined}>
        {total > 0 ? (
          <>
            <div className="mb-1 mt-2 flex h-2 overflow-hidden rounded-full bg-[#eceef2]" role="img" aria-label="Where visits came from">
              {t.channels.map((c, i) => <i key={c.key} style={{ width: `${(c.sessions / total) * 100}%`, background: MIX[i % MIX.length] }} />)}
            </div>
            <p className="text-xs text-[var(--text-secondary)]">{t.channels.map((c) => c.label).join(" · ")}</p>
          </>
        ) : null}
      </StatCard>
      <StatCard
        label="Organic sessions"
        source="GA4"
        value={num(organic.current)}
        change={pair(organic)}
        changeNote={organic.previous != null ? `vs ${prior} · was ${num(organic.previous)}` : undefined}
        note="Visits that came from search engines"
        facts={[
          ...(mix.ai_referral ? ([["AI referrals", <>{num(mix.ai_referral.sessions)}<Delta key="d" pct={mix.ai_referral.change_pct} /></>]] as [string, ReactNode][]) : []),
          ...(review.has_search_data ? ([["Search Console clicks", <>{num(review.search.clicks.current)}<Delta key="d" pct={pair(review.search.clicks)} /></>]] as [string, ReactNode][]) : []),
        ]}
      />
      <StatCard label="Other channels" source="GA4" value="" note="Sessions this month" facts={others.map((c) => [c.label, <>{num(c.sessions)}<Delta key="d" pct={c.change_pct} /></>] as [string, ReactNode])} />
    </div>
  );
}

export function LeadsCards({ review, cards }: { review: Review; cards: Scorecards }) {
  const c = cards.conversions;
  const prior = monthLabel(cards.previous_month).split(" ")[0];
  const rev = review.revenue?.status === "measured" ? review.revenue : null;
  const noun = c.noun.charAt(0).toUpperCase() + c.noun.slice(1);
  return (
    <div className="grid gap-3 @3xl:grid-cols-2">
      <StatCard
        label={noun}
        source="GA4"
        value={num(c.headline)}
        change={c.change_pct}
        changeNote={c.previous != null ? `vs ${prior} · was ${num(c.previous)}` : undefined}
        bar={c.goal ? c.goal_progress_pct ?? 0 : undefined}
        note={c.goal ? `${c.goal_progress_pct != null ? `${Math.round(c.goal_progress_pct)}% of ` : ""}${num(c.goal)} · goal for the period` : undefined}
        facts={c.top.map((r) => [r.label, <>{num(r.count)}<Delta key="d" pct={r.change_pct} /></>] as [string, ReactNode])}
      />
      {rev ? (
        <StatCard
          label="Revenue"
          source="GA4"
          value={money(rev.revenue.current)}
          change={rev.revenue.change_pct}
          changeNote={rev.revenue.previous != null ? `vs ${prior} · was ${money(rev.revenue.previous)}` : undefined}
          facts={[["Through organic search", money(rev.organic_revenue.current)]]}
        />
      ) : (
        <StatCard
          label="Conversion rate"
          source="GA4"
          value={`${num(review.conversion_rate.current, 2)}%`}
          change={review.conversion_rate.change_pct}
          changeNote={review.conversion_rate.previous != null ? `vs ${prior} · was ${num(review.conversion_rate.previous, 2)}%` : undefined}
        />
      )}
    </div>
  );
}
