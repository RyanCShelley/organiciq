"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { clearFocusAction, saveFocusAction } from "@/app/(app)/[clientSlug]/focus/actions";
import type { Client } from "@/lib/api";
import type { BucketOverview } from "@/lib/engine";
import { FOCUSES, monthLabel, type ClientFocus, type FocusValue } from "@/lib/focus";
import type { EngineNumbers, Pair, Review, VisibilityTerm } from "@/lib/review";

const num = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });
const money = (n: number | null | undefined) =>
  n == null ? "–" : n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** The change since last month, green when it is the direction we want. */
function Change({ pair, lowerIsBetter = false, previousLabel }: { pair: Pair; lowerIsBetter?: boolean; previousLabel: string }) {
  if (pair.change_pct == null) {
    return <span className="text-xs text-[var(--text-tertiary)]">{pair.previous == null ? `no ${previousLabel} figure` : "no change to show"}</span>;
  }
  const up = pair.change_pct > 0;
  const good = lowerIsBetter ? !up : up;
  const flat = Math.abs(pair.change_pct) < 1;
  return (
    <span className={`text-xs font-semibold ${flat ? "text-[var(--text-secondary)]" : good ? "text-green-700" : "text-red-700"}`}>
      {flat ? "flat" : `${up ? "▲" : "▼"} ${Math.abs(pair.change_pct).toFixed(0)}%`}{" "}
      <span className="font-normal text-[var(--text-secondary)]">vs {previousLabel}</span>
    </span>
  );
}

function Card({
  label,
  value,
  pair,
  format = num,
  lowerIsBetter,
  previousLabel,
  note,
}: {
  label: string;
  value: string;
  pair: Pair;
  format?: (n: number | null) => string;
  lowerIsBetter?: boolean;
  previousLabel: string;
  note?: string;
}) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      <div className="mt-1">
        <Change pair={pair} lowerIsBetter={lowerIsBetter} previousLabel={previousLabel} />
      </div>
      {pair.previous != null ? (
        <div className="text-xs text-[var(--text-tertiary)]">was {format(pair.previous)}</div>
      ) : null}
      {note ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{note}</div> : null}
    </div>
  );
}

const STATUS_STYLE: Record<string, string> = {
  "Top 3": "bg-green-50 text-green-800",
  "Page 1": "bg-green-50 text-green-800",
  "Page 2": "bg-amber-50 text-amber-800",
  "Beyond page 2": "bg-[var(--bg)] text-[var(--text-secondary)]",
  "Barely showing": "bg-[var(--bg)] text-[var(--text-secondary)]",
  "Not showing": "bg-red-50 text-red-800",
};

/** A position moved by this many places; lower is better, so a smaller number is an improvement. */
function PositionCell({ pair }: { pair: Pair }) {
  if (pair.current == null) return <span className="text-[var(--text-tertiary)]">–</span>;
  const gain = pair.previous != null ? pair.previous - pair.current : null;
  return (
    <span className="tabular-nums">
      {pair.current.toFixed(1)}
      {gain != null && Math.abs(gain) >= 0.5 ? (
        <span className={`ml-1 text-xs ${gain > 0 ? "text-green-700" : "text-red-700"}`}>
          {gain > 0 ? "▲" : "▼"}
          {Math.abs(gain).toFixed(1)}
        </span>
      ) : null}
    </span>
  );
}

function ImpressionsCell({ pair }: { pair: Pair }) {
  const change = pair.change_pct;
  return (
    <span className="tabular-nums">
      {num(pair.current)}
      {change != null && Math.abs(change) >= 1 ? (
        <span className={`ml-1 text-xs ${change > 0 ? "text-green-700" : "text-red-700"}`}>
          {change > 0 ? "▲" : "▼"}
          {Math.abs(change).toFixed(0)}%
        </span>
      ) : null}
    </span>
  );
}

function TermRow({ term, showBing }: { term: VisibilityTerm; showBing: boolean }) {
  const g: EngineNumbers = term.google;
  const b: EngineNumbers = term.bing;
  const base = term.status.replace(" (Bing)", "");
  return (
    <tr className="border-t border-[var(--border)] align-top">
      <td className="min-w-[11rem] py-2 pr-3">
        <div className="font-medium">{term.keyword}</div>
        {term.prompt ? <div className="mt-0.5 max-w-[22rem] text-xs italic text-[var(--text-tertiary)]">Prompt: {term.prompt}</div> : null}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{num(term.volume)}</td>
      <td className="px-3 py-2 text-right"><ImpressionsCell pair={g.impressions} /></td>
      <td className="px-3 py-2 text-right"><PositionCell pair={g.position} /></td>
      <td className="px-3 py-2 text-right tabular-nums">{num(g.clicks.current)}</td>
      {showBing ? (
        <>
          <td className="px-3 py-2 text-right"><ImpressionsCell pair={b.impressions} /></td>
          <td className="px-3 py-2 text-right"><PositionCell pair={b.position} /></td>
        </>
      ) : null}
      <td className="py-2 pl-3">
        <span className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[base] ?? STATUS_STYLE["Not showing"]}`}>
          {term.status}
        </span>
      </td>
    </tr>
  );
}

function FocusPanel({
  client,
  planMonth,
  focus,
  buckets,
  reach,
}: {
  client: Client;
  planMonth: string;
  focus: ClientFocus | null;
  buckets: { id: string; name: string }[];
  reach: BucketOverview[];
}) {
  const [choice, setChoice] = useState<FocusValue | null>(focus?.focus ?? null);
  const [bucketId, setBucketId] = useState(focus?.bucket_id ?? "");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const picked = reach.find((x) => x.id === bucketId);
  const thinPick = picked && picked.reach === "thin" ? picked : null;
  const better = [...reach].filter((x) => x.id !== bucketId && x.strong > 0).sort((a, b) => b.expected_extra_clicks - a.expected_extra_clicks)[0];

  function run(task: () => Promise<{ ok: true } | { ok: false; error: string }>, then?: () => void) {
    setError(null);
    setSaved(false);
    startTransition(async () => {
      const result = await task();
      if (result.ok) {
        setSaved(true);
        then?.();
      } else setError(result.error);
    });
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-sm font-semibold">Choose the focus for {monthLabel(planMonth)}</h2>
      <div className="mt-3 space-y-2">
        {FOCUSES.map((option) => (
          <label
            key={option.value}
            className={`flex cursor-pointer items-start gap-3 rounded-lg border p-3 text-sm ${
              choice === option.value ? "border-[var(--brand-teal)] bg-[var(--brand-teal)]/10" : "border-[var(--border)] hover:border-[var(--brand-teal)]"
            }`}
          >
            <input
              type="radio"
              name="focus"
              checked={choice === option.value}
              onChange={() => {
                setChoice(option.value);
                setSaved(false);
              }}
              className="mt-1"
            />
            <span>
              <span className="block font-semibold">{option.label}</span>
              <span className="text-[var(--text-secondary)]">{option.hint}</span>
            </span>
          </label>
        ))}
      </div>
      <label className="mt-3 block text-sm">
        <span className="font-semibold">Watchlist bucket</span>
        <select
          value={bucketId}
          onChange={(e) => {
            setBucketId(e.target.value);
            setSaved(false);
          }}
          className="mt-1 w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm"
        >
          <option value="">{buckets.length ? "No bucket chosen" : "No buckets: import the watchlist in Settings"}</option>
          {buckets.map((b) => {
            const r = reach.find((x) => x.id === b.id);
            return (
              <option key={b.id} value={b.id}>
                {b.name}
                {choice === "visibility" && r ? ` (${r.reach === "thin" ? "little to move" : `${r.strong} strong, +${Math.round(r.expected_extra_clicks)} clicks`})` : ""}
              </option>
            );
          })}
        </select>
        {choice === "visibility" && thinPick ? (
          <span className="mt-2 block rounded-lg bg-amber-50 p-3 text-xs text-amber-900">
            {thinPick.name} has almost nothing in reach for Visibility ({thinPick.found} searches, none strong), so
            it would be a content job.
            {better ? ` ${better.name} has ${better.strong} strong searches (+${Math.round(better.expected_extra_clicks)} clicks).` : ""}
          </span>
        ) : null}
      </label>
      <div className="mt-4 flex items-center gap-3">
        <button
          type="button"
          disabled={pending || !choice}
          onClick={() => run(() => saveFocusAction(client.id, client.slug, planMonth, choice as string, bucketId || null))}
          className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Save focus
        </button>
        {focus ? (
          <button
            type="button"
            disabled={pending}
            onClick={() =>
              run(
                () => clearFocusAction(client.id, client.slug, planMonth),
                () => {
                  setChoice(null);
                  setBucketId("");
                },
              )
            }
            className="text-sm font-semibold text-red-700 hover:underline disabled:opacity-50"
          >
            Clear
          </button>
        ) : null}
        {saved ? <span className="text-sm text-[var(--text-secondary)]">Saved.</span> : null}
      </div>
      {error ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function ReviewScreen({
  client,
  month,
  planMonth,
  review,
  error,
  focus,
  buckets,
  reach,
}: {
  client: Client;
  month: string;
  planMonth: string;
  review: Review | null;
  error: string | null;
  focus: ClientFocus | null;
  buckets: { id: string; name: string }[];
  reach: BucketOverview[];
}) {
  const router = useRouter();
  const [copied, setCopied] = useState(false);
  const prior = review ? monthLabel(review.previous_month).split(" ")[0] : "last month";
  const noun = review?.noun ?? "leads";

  return (
    <section className="max-w-6xl">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">{client.client_name}</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Monthly review · {monthLabel(month)}</p>
        </div>
        <input
          type="month"
          value={month}
          aria-label="Month to review"
          onChange={(e) => e.target.value && router.push(`/${client.slug}/review?month=${e.target.value}`)}
          className="rounded-lg border border-[var(--border)] px-3 py-1.5 text-sm"
        />
      </header>

      {error ? (
        <p role="alert" className="mb-6 rounded-lg bg-red-50 p-4 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <div className="min-w-0 space-y-6">
          {review ? (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <Card label={noun} value={num(review.conversions.current)} pair={review.conversions} previousLabel={prior} />
                {review.revenue?.status === "measured" ? (
                  <Card
                    label="Revenue"
                    value={money(review.revenue.revenue.current)}
                    pair={review.revenue.revenue}
                    format={money}
                    previousLabel={prior}
                    note={`${money(review.revenue.organic_revenue.current)} through organic search`}
                  />
                ) : (
                  <Card label="Conversion rate" value={`${num(review.conversion_rate.current, 2)}%`} pair={review.conversion_rate} previousLabel={prior} />
                )}
                <Card label="Sessions" value={num(review.sessions.current)} pair={review.sessions} previousLabel={prior} />
                <Card label="Organic sessions" value={num(review.organic_sessions.current)} pair={review.organic_sessions} previousLabel={prior} />
                {review.has_search_data ? (
                  <>
                    <Card label="Search clicks" value={num(review.search.clicks.current)} pair={review.search.clicks} previousLabel={prior} />
                    <Card
                      label="Avg. search position"
                      value={num(review.search.average_position.current, 1)}
                      pair={review.search.average_position}
                      lowerIsBetter
                      format={(n) => num(n, 1)}
                      previousLabel={prior}
                    />
                  </>
                ) : (
                  <div className="rounded-xl border border-dashed border-[var(--border)] p-4 text-sm text-[var(--text-secondary)] sm:col-span-2">
                    No Search Console data for {monthLabel(month)}. Pull it from Settings → Connections once GSC is
                    connected.
                  </div>
                )}
              </div>

              {review.revenue?.status === "unavailable" ? (
                <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">Revenue: {review.revenue.reason}</p>
              ) : null}

              {review.goal.period_goal ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
                  <div className="flex items-baseline justify-between">
                    <h2 className="text-sm font-semibold">Against the goal</h2>
                    <span className="text-sm tabular-nums">
                      {num(review.conversions.current)} of {num(review.goal.period_goal)} {noun}
                      {review.goal.progress_pct != null ? ` (${review.goal.progress_pct.toFixed(0)}%)` : ""}
                    </span>
                  </div>
                  <div className="mt-2 h-2 rounded bg-[var(--border)]">
                    <div
                      className={`h-2 rounded ${(review.goal.progress_pct ?? 0) >= 100 ? "bg-green-600" : "bg-[var(--brand-teal)]"}`}
                      style={{ width: `${Math.min(100, review.goal.progress_pct ?? 0)}%` }}
                    />
                  </div>
                  <p className="mt-2 text-xs text-[var(--text-secondary)]">
                    {review.goal.checkpoint
                      ? `${review.goal.checkpoint.month}-month checkpoint (due ${review.goal.checkpoint.due}): ${num(review.goal.checkpoint.projected)} a month. `
                      : ""}
                    {review.goal.final_goal ? `12-month goal: ${num(review.goal.final_goal)} a month. ` : ""}
                    {review.goal.baseline_version ? `From baseline version ${review.goal.baseline_version}.` : ""}
                  </p>
                </div>
              ) : (
                <p className="rounded-lg bg-[var(--bg)] p-3 text-sm text-[var(--text-secondary)]">
                  No goal yet: lock a baseline in Settings → Baseline &amp; goals.
                </p>
              )}

              <div className="grid gap-6 md:grid-cols-2">
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
                  <h2 className="text-sm font-semibold">Where visits came from</h2>
                  <table className="mt-3 w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                      <tr>
                        <th className="py-1 font-medium">Channel</th>
                        <th className="py-1 text-right font-medium">Sessions</th>
                        <th className="py-1 text-right font-medium">{noun}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...review.channels]
                        .sort((a, b) => b.sessions - a.sessions)
                        .slice(0, 6)
                        .map((c) => (
                          <tr key={c.label} className="border-t border-[var(--border)]">
                            <td className="py-1.5">{c.label}</td>
                            <td className="py-1.5 text-right tabular-nums">{num(c.sessions)}</td>
                            <td className="py-1.5 text-right tabular-nums">{num(c.conversions)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                  {review.services.rows[0] ? (
                    <p className="mt-3 text-xs text-[var(--text-secondary)]">
                      OrganicIQ channels (organic, AI, direct, referral): {num(review.services.rows[0].sessions.current)} sessions,{" "}
                      {num(review.services.rows[0].lead_events.current)} conversion events.
                    </p>
                  ) : null}
                </div>

                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
                  <h2 className="text-sm font-semibold">Top pages</h2>
                  <table className="mt-3 w-full text-left text-sm">
                    <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                      <tr>
                        <th className="py-1 font-medium">Page</th>
                        <th className="py-1 text-right font-medium">Sessions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {review.top_pages.map((p) => (
                        <tr key={p.page} className="border-t border-[var(--border)]">
                          <td className="max-w-[14rem] truncate py-1.5" title={p.page}>
                            {p.page.replace(/^https?:\/\/[^/]+/, "") || "/"}
                          </td>
                          <td className="py-1.5 text-right tabular-nums">{num(p.sessions)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              {review.visibility ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h2 className="text-sm font-semibold">Visibility: the watchlist in Google and Bing</h2>
                    <span className="text-xs text-[var(--text-secondary)]">
                      {review.visibility.summary.showing_in_google} of {review.visibility.summary.terms} terms showed in Google ·{" "}
                      {review.visibility.summary.on_page_one} on page one
                      {review.visibility.bing.has_data ? ` · ${review.visibility.summary.showing_in_bing} in Bing` : ""}
                    </span>
                  </div>
                  {!review.visibility.has_google_data ? (
                    <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                      No Search Console data for these terms yet, so nothing is shown for Google.
                    </p>
                  ) : null}
                  <div className="mt-3 space-y-5 overflow-x-auto">
                    {review.visibility.buckets.map((bucket) => (
                      <div key={bucket.id}>
                        <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-secondary)]">
                          {bucket.name}
                        </h3>
                        <table className="mt-1 w-full min-w-[34rem] text-left text-sm">
                          <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                            <tr>
                              <th className="py-1 pr-3 font-medium">Term</th>
                              <th className="px-3 py-1 text-right font-medium">Volume</th>
                              <th className="px-3 py-1 text-right font-medium">Google impr.</th>
                              <th className="px-3 py-1 text-right font-medium">Google pos.</th>
                              <th className="px-3 py-1 text-right font-medium">Clicks</th>
                              {review.visibility?.bing.has_data ? (
                                <>
                                  <th className="px-3 py-1 text-right font-medium">Bing impr.</th>
                                  <th className="px-3 py-1 text-right font-medium">Bing pos.</th>
                                </>
                              ) : null}
                              <th className="py-1 pl-3 font-medium">Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {bucket.terms.map((term) => (
                              <TermRow key={term.keyword} term={term} showBing={review.visibility?.bing.has_data ?? false} />
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>
                  <ul className="mt-4 space-y-1 text-xs text-[var(--text-tertiary)]">
                    <li>
                      Each term is matched to the exact search; a longer phrase the site shows for is not counted here, so
                      these numbers understate it. Position is the average across impressions, and under 10 impressions it
                      is not meaningful. Arrows compare with {prior}.
                    </li>
                    {review.visibility.bing.has_data ? <li>{review.visibility.bing.note}</li> : <li>No Bing data pulled yet.</li>}
                    <li>AI prompt results: {review.visibility.ai_prompts}</li>
                  </ul>
                </div>
              ) : null}
            </>
          ) : null}
        </div>

        <aside className="space-y-4 lg:sticky lg:top-6 lg:self-start">
          {review ? (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">Summary</h2>
                <button
                  type="button"
                  onClick={async () => {
                    await navigator.clipboard.writeText(review.summary.join("\n"));
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  }}
                  className="text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                >
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <ul className="mt-3 space-y-2 text-sm">
                {review.summary.map((line) => (
                  <li key={line} className="text-[var(--text-secondary)]">
                    {line}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                Worked out from the numbers on the left. It says what moved, not why.
              </p>
            </div>
          ) : null}
          <FocusPanel key={planMonth} client={client} planMonth={planMonth} focus={focus} buckets={buckets} reach={reach} />
        </aside>
      </div>
    </section>
  );
}
