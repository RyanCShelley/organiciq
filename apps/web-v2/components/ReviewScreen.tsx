"use client";

import { useRouter } from "next/navigation";
import { Fragment, useEffect, useState, useTransition } from "react";

import { clearFocusAction, saveFocusAction } from "@/app/(app)/[clientSlug]/focus/actions";
import { reachAction, rerunReviewAction } from "@/app/(app)/[clientSlug]/review/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { BucketOverview, ShippedResult } from "@/lib/engine";
import { FOCUSES, monthLabel, type ClientFocus, type FocusValue } from "@/lib/focus";
import type { Pair, Review, Visibility, VisibilityAi, VisibilityTerm } from "@/lib/review";

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
    <div className="max-w-sm rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 @4xl:max-w-none">
      <h2 className="text-sm font-semibold">Focus for {monthLabel(planMonth)}</h2>
      <div className="mt-2 space-y-1.5">
        {FOCUSES.map((option) => (
          <label
            key={option.value}
            className={`flex cursor-pointer items-center gap-2.5 rounded-lg border px-2.5 py-2 text-sm ${
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
              className="shrink-0"
            />
            <span className="min-w-0">
              <span className="block font-semibold leading-tight">{option.label}</span>
              <span className="block text-xs text-[var(--text-secondary)]">{option.hint}</span>
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
          className="rounded-lg bg-[#00a99d] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--brand-teal-hover)] disabled:cursor-not-allowed disabled:hover:bg-[#00a99d]"
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

const aiPts = (n: number | null) => (n == null || n === 0 ? null : `${n > 0 ? "▲" : "▼"} ${Math.abs(Math.round(n * 100))} pts`);

const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const signed = (n: number) => `${n > 0 ? "+" : ""}${n.toLocaleString()}`;
const shortDate = (iso: string | null) => (iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "");

/** What the work shipped earlier did: 28 days before against 28 days after, with no verdict. */
function ShippedWork({ rows }: { rows: ShippedResult[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="text-sm font-semibold">Work we shipped: what it did</h2>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">
        Searches for the topic on that page, the 28 days before it shipped against the 28 days after. A small page moves by chance, so read these as direction, not proof.
      </p>
      <ul className="mt-3 divide-y divide-[var(--border)]">
        {rows.map((r) => (
          <li key={r.task_id} className="py-3 text-sm">
            <div className="font-medium">{r.title}</div>
            <div className="text-xs text-[var(--text-secondary)]">
              “{r.topic}” · {shortPage(r.page)} · shipped {shortDate(r.shipped_on)}
            </div>
            {r.status === "measuring" && r.before ? (
              <p className="mt-1 text-[var(--text-secondary)]">
                Measuring until {shortDate(r.check_on)}. Before: {r.before.clicks.toLocaleString()} clicks, {r.before.impressions.toLocaleString()} impressions
                {r.before.position != null ? `, position ${r.before.position}` : ""}.
              </p>
            ) : null}
            {r.status === "measured" && r.before && r.after && r.change ? (
              <div className="mt-1 grid gap-x-6 gap-y-1 text-[var(--text-secondary)] sm:grid-cols-3">
                <span>
                  Clicks {r.before.clicks.toLocaleString()} → {r.after.clicks.toLocaleString()}{" "}
                  <strong className={r.change.clicks > 0 ? "text-green-700" : r.change.clicks < 0 ? "text-red-700" : ""}>({signed(r.change.clicks)})</strong>
                </span>
                <span>
                  Impressions {r.before.impressions.toLocaleString()} → {r.after.impressions.toLocaleString()}{" "}
                  <strong className={r.change.impressions > 0 ? "text-green-700" : r.change.impressions < 0 ? "text-red-700" : ""}>({signed(r.change.impressions)})</strong>
                </span>
                <span>
                  Position {r.before.position ?? "–"} → {r.after.position ?? "–"}
                  {r.change.position != null ? (
                    <strong className={r.change.position < 0 ? "ml-1 text-green-700" : r.change.position > 0 ? "ml-1 text-red-700" : "ml-1"}>
                      ({signed(r.change.position)}{r.change.position < 0 ? ", better" : r.change.position > 0 ? ", worse" : ""})
                    </strong>
                  ) : null}
                </span>
              </div>
            ) : null}
            {r.status === "measured" && (r.ai_before || r.ai_after) ? (
              <p className="mt-1 text-xs text-[var(--text-secondary)]">
                AI platforms citing the site for this topic: {r.ai_before ? `${r.ai_before.cited} of ${r.ai_before.platforms}` : "no run before"} →{" "}
                {r.ai_after ? `${r.ai_after.cited} of ${r.ai_after.platforms}` : "no run since"}.
              </p>
            ) : null}
            {r.note ? <p className="mt-1 text-xs text-amber-800">{r.note}</p> : null}
            {r.status === "no_baseline" ? <p className="mt-1 text-xs text-[var(--text-tertiary)]">No starting numbers were recorded for this one.</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}


const PLATFORM_ORDER = ["ChatGPT", "Claude", "Gemini", "Perplexity"];
type Filter = "all" | "showing" | "not" | "page1" | "ai";

/** The watchlist in Google, Bing and the AI platforms: one line per term, no sideways scrolling. */
function VisibilityPanel({ visibility, prior, href }: { visibility: Visibility; prior: string; href: string }) {
  const [filter, setFilter] = useState<Filter>("all");
  const all = visibility.buckets.flatMap((b) => b.terms);
  const showing = (t: VisibilityTerm) => (t.google.impressions.current ?? 0) > 0;
  const pageOne = (t: VisibilityTerm) => t.status.startsWith("Top 3") || t.status.startsWith("Page 1");
  const aiCited = (t: VisibilityTerm) => (t.ai?.cited ?? 0) > 0;
  const keep: Record<Filter, (t: VisibilityTerm) => boolean> = {
    all: () => true,
    showing,
    not: (t) => !showing(t),
    page1: pageOne,
    ai: aiCited,
  };
  const chips: [Filter, string, number][] = [
    ["all", "All", all.length],
    ["showing", "Showing", all.filter(showing).length],
    ["not", "Not showing", all.filter((t) => !showing(t)).length],
    ["page1", "Page one", all.filter(pageOne).length],
    ["ai", "AI cited", all.filter(aiCited).length],
  ];
  const llm = visibility.llm;
  const rate = llm?.summary.visibility_rate;
  const bing = visibility.bing.has_data;
  const tile = "rounded-lg bg-[var(--bg)] px-3 py-2";
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold">Visibility: the watchlist in Google, Bing and AI platforms</h2>
        <a href={href} className="text-xs font-semibold text-[var(--brand-teal)] hover:underline">Open LLM visibility →</a>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 @3xl:grid-cols-4">
        <div className={tile}>
          <div className="text-xs text-[var(--text-secondary)]">Terms showing in Google</div>
          <div className="text-xl font-semibold tabular-nums">{visibility.summary.showing_in_google} of {visibility.summary.terms}</div>
        </div>
        <div className={tile}>
          <div className="text-xs text-[var(--text-secondary)]">On page one</div>
          <div className="text-xl font-semibold tabular-nums">{visibility.summary.on_page_one}</div>
        </div>
        <div className={tile}>
          <div className="text-xs text-[var(--text-secondary)]">Clicks from these terms</div>
          <div className="text-xl font-semibold tabular-nums">{num(visibility.summary.google_clicks)}</div>
        </div>
        <div className={tile} title={llm ? (llm.in_month ? `Run of ${llm.run_date}` : `Latest run, ${llm.run_date}, after this month`) : undefined}>
          <div className="text-xs text-[var(--text-secondary)]">AI answers naming or citing us</div>
          {rate ? (
            <div className="text-xl font-semibold tabular-nums">
              {Math.round(rate.current * 100)}%
              {aiPts(rate.delta) ? <span className={`ml-2 text-xs ${(rate.delta ?? 0) > 0 ? "text-green-700" : "text-red-700"}`}>{aiPts(rate.delta)}</span> : null}
            </div>
          ) : (
            <div className="text-sm text-[var(--text-tertiary)]">no run yet</div>
          )}
        </div>
      </div>
      {llm ? (
        <p className="mt-2 text-xs text-[var(--text-secondary)]">
          {llm.in_month ? `AI run of ${llm.run_date}` : `Latest AI run, ${llm.run_date}, after this month`}
          {llm.previous_run_date ? `, against ${llm.previous_run_date}` : ", the first run"} · {llm.platforms.map((p) => `${p.platform} ${Math.round(p.visibility_rate.current * 100)}%`).join(" · ")}
          {llm.brand_check.length > 0 ? ` · asked by name, the site was cited by ${llm.brand_check.map((p) => `${p.platform} ${p.site_cited}/${p.answers}`).join(", ")}` : ""}
        </p>
      ) : null}

      {!visibility.has_google_data ? (
        <p className="mt-3 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">No Search Console data for these terms yet, so nothing is shown for Google.</p>
      ) : null}

      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Filter terms">
        {chips.map(([id, label, n]) => (
          <button
            key={id}
            type="button"
            onClick={() => setFilter(id)}
            aria-pressed={filter === id}
            className={`rounded-full border px-3 py-1 text-xs font-semibold ${filter === id ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)]"}`}
          >
            {label} {n}
          </button>
        ))}
      </div>

      <table className="mt-3 w-full table-fixed text-left text-sm">
        <colgroup>
          <col style={{ width: "25%" }} />
          <col style={{ width: "9%" }} />
          <col style={{ width: "15%" }} />
          <col style={{ width: "11%" }} />
          <col style={{ width: "7%" }} />
          {bing ? <col style={{ width: "11%" }} /> : null}
          <col style={{ width: "9%" }} />
          <col style={{ width: "13%" }} />
        </colgroup>
        <thead className="text-[0.65rem] uppercase text-[var(--text-tertiary)]">
          <tr>
            <th className="py-1 pr-2 font-medium">Term</th>
            <th className="px-1 py-1 text-right font-medium">Volume</th>
            <th className="px-1 py-1 text-right font-medium">Google impr.</th>
            <th className="px-1 py-1 text-right font-medium">Position</th>
            <th className="px-1 py-1 text-right font-medium">Clicks</th>
            {bing ? <th className="px-1 py-1 text-right font-medium">Bing</th> : null}
            <th className="px-1 py-1 text-right font-medium">AI</th>
            <th className="py-1 pl-2 text-right font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {visibility.buckets.map((bucket, index) => {
            const terms = bucket.terms.filter(keep[filter]);
            if (terms.length === 0) return null;
            const first = visibility.buckets.slice(0, index).every((b) => b.terms.filter(keep[filter]).length === 0);
            const impressions = terms.reduce((n, t) => n + (t.google.impressions.current ?? 0), 0);
            return (
              <Fragment key={bucket.id}>
                {first ? null : (
                  <tr aria-hidden="true">
                    <td colSpan={bing ? 8 : 7} className="h-6 p-0" />
                  </tr>
                )}
                <tr className="bg-[var(--brand-teal)]/10">
                  <td colSpan={bing ? 8 : 7} className="border-l-4 border-[var(--brand-teal)] px-3 py-2.5">
                    <span className="text-sm font-bold text-[var(--text-primary)]">{bucket.name}</span>
                    <span className="ml-3 text-xs font-normal text-[var(--text-secondary)]">
                      {terms.length} term{terms.length === 1 ? "" : "s"} · {num(impressions)} impression{impressions === 1 ? "" : "s"}
                    </span>
                  </td>
                </tr>
                {terms.map((t) => {
                  const base = t.status.replace(" (Bing)", "");
                  return (
                    <tr key={t.keyword} className="border-t border-[var(--border)]">
                      <td className="truncate py-1.5 pr-2 font-medium" title={t.prompt ? `${t.keyword}\nAI prompt: ${t.prompt}` : t.keyword}>{t.keyword}</td>
                      <td className="px-1 py-1.5 text-right tabular-nums">{num(t.volume)}</td>
                      <td className="px-1 py-1.5 text-right"><ImpressionsCell pair={t.google.impressions} /></td>
                      <td className="px-1 py-1.5 text-right"><PositionCell pair={t.google.position} /></td>
                      <td className="px-1 py-1.5 text-right tabular-nums">{num(t.google.clicks.current)}</td>
                      {bing ? (
                        <td className="px-1 py-1.5 text-right text-xs tabular-nums text-[var(--text-secondary)]">
                          {(t.bing.impressions.current ?? 0) > 0 ? `${num(t.bing.impressions.current)} · ${t.bing.position.current?.toFixed(1) ?? "–"}` : "–"}
                        </td>
                      ) : null}
                      <td className="px-1 py-1.5 text-right">
                        {t.ai ? (
                          <span className="inline-flex gap-1" title={PLATFORM_ORDER.map((p) => `${p}: ${t.ai?.by_platform[p] ? (t.ai.by_platform[p].cited ? "cited" : t.ai.by_platform[p].named ? "named, not cited" : "not visible") : "not asked"}`).join("\n")}>
                            {PLATFORM_ORDER.map((p) => {
                              const r = t.ai?.by_platform[p];
                              return (
                                <i
                                  key={p}
                                  aria-label={`${p}: ${r ? (r.cited ? "cited" : r.named ? "named" : "not visible") : "not asked"}`}
                                  className={`inline-block h-2.5 w-2.5 rounded-full border ${r?.cited ? "border-green-700 bg-green-700" : r?.named ? "border-amber-600 bg-amber-300" : "border-[var(--border-strong,#bbb)]"}`}
                                />
                              );
                            })}
                          </span>
                        ) : (
                          <span className="text-xs text-[var(--text-tertiary)]">{t.prompt ? "–" : "no prompt"}</span>
                        )}
                      </td>
                      <td className="py-1.5 pl-2 text-right">
                        <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${STATUS_STYLE[base] ?? STATUS_STYLE["Not showing"]}`}>{base.replace("Beyond page 2", "Page 3+").replace("Barely showing", "Barely")}</span>
                      </td>
                    </tr>
                  );
                })}
              </Fragment>
            );
          })}
        </tbody>
      </table>
      {all.filter(keep[filter]).length === 0 ? <p className="mt-3 text-sm text-[var(--text-tertiary)]">No terms match this filter.</p> : null}

      <p className="mt-3 text-xs text-[var(--text-tertiary)]">
        AI dots are ChatGPT, Claude, Gemini and Perplexity: green cited the site, amber named the brand only, empty did not show it. Hover a term for its prompt and a dot for its platform. Arrows compare with {prior}.
        {" "}Terms match the exact search, so a longer phrase the site shows for isn&apos;t counted here. {bing ? "Bing reports weekly; a week counts toward the month it starts in." : "No Bing data pulled yet."}
      </p>
    </div>
  );
}

function LockLine({ review, clientId, slug, month }: { review: Review; clientId: string; slug: string; month: string }) {
  const router = useRouter();
  const [pending, start] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const rerun = () => {
    if (!window.confirm("Work this month out again from the data held now? It replaces the review that was kept.")) return;
    start(async () => {
      setError(null);
      const r = await rerunReviewAction(clientId, slug, month);
      if (r.ok) router.refresh();
      else setError(r.error);
    });
  };
  return (
    <p className="mt-1 text-xs text-[var(--text-secondary)]">
      {review.locked ? (
        <>
          <span className="font-semibold text-green-800">Locked</span> on {review.locked_at ? new Date(review.locked_at).toLocaleDateString("en-US", { month: "short", day: "numeric" }) : "an earlier day"}
          {review.data_through?.search_console ? `, from data through ${new Date(`${review.data_through.search_console}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" })}` : ""}.{" "}
          <button type="button" onClick={rerun} disabled={pending} className="font-semibold underline disabled:opacity-50">
            {pending ? <><Spinner />Working it out again…</> : "Work it out again"}
          </button>
        </>
      ) : (
        <>
          <span className="font-semibold text-amber-800">Not locked.</span> {review.lock_note}
        </>
      )}
      {error ? <span role="alert" className="ml-2 text-red-700">{error}</span> : null}
    </p>
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
  shipped,
}: {
  client: Client;
  month: string;
  planMonth: string;
  review: Review | null;
  error: string | null;
  focus: ClientFocus | null;
  buckets: { id: string; name: string }[];
  shipped: ShippedResult[];
}) {
  const router = useRouter();
  // How much each bucket has in reach is a hint beside the focus choice. It is the slowest part of the page, so it
  // arrives after the review has shown instead of holding it up.
  const [reach, setReach] = useState<BucketOverview[]>([]);
  useEffect(() => {
    let live = true;
    reachAction(client.id, month).then((r) => live && setReach(r));
    return () => {
      live = false;
    };
  }, [client.id, month]);
  const [copied, setCopied] = useState(false);
  const prior = review ? monthLabel(review.previous_month).split(" ")[0] : "last month";
  const noun = review?.noun ?? "leads";

  return (
    <section className="@container max-w-6xl">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">{client.client_name}</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">Monthly review · {monthLabel(month)}</p>
          {review ? <LockLine review={review} clientId={client.id} slug={client.slug} month={month} /> : null}
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

      <div className="mb-6 grid items-start gap-6 @4xl:grid-cols-[minmax(0,1fr)_16rem]">

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
              <div className="mt-3 space-y-4">
                {review.summary_sections.map((section) => (
                  <div key={section.title}>
                    <h3 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{section.title}</h3>
                    <dl className="mt-1 divide-y divide-[var(--border)]">
                      {section.rows.map((row) => (
                        <div key={row.label} className="py-2">
                          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                            <dt className="text-sm font-semibold">{row.label}</dt>
                            <dd className="flex flex-wrap items-baseline gap-2 text-right">
                              <span className="text-base font-semibold tabular-nums">{row.value}</span>
                              {row.change ? (
                                <span
                                  className={`rounded px-1.5 py-0.5 text-xs font-semibold ${row.change.tone === "good" ? "bg-green-50 text-green-800" : row.change.tone === "bad" ? "bg-red-50 text-red-800" : "bg-[var(--bg)] text-[var(--text-secondary)]"}`}
                                  title={row.change.against}
                                >
                                  {row.change.tone === "good" ? "▲ " : row.change.tone === "bad" ? "▼ " : "• "}
                                  {row.change.text}
                                </span>
                              ) : null}
                            </dd>
                          </div>
                          {row.change ? <p className="text-xs text-[var(--text-tertiary)]">{row.change.against}</p> : null}
                          {row.detail ? <p className="text-xs text-[var(--text-secondary)]">{row.detail}</p> : null}
                        </div>
                      ))}
                    </dl>
                  </div>
                ))}
              </div>
              <p className="mt-3 text-xs text-[var(--text-tertiary)]">
                Worked out from the numbers below. It says what moved, not why.
              </p>
            </div>
          ) : null}
          <FocusPanel key={planMonth} client={client} planMonth={planMonth} focus={focus} buckets={buckets} reach={reach} />
        
      </div>

      <div>
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

              <div className="grid gap-6 @2xl:grid-cols-2">
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
              <ShippedWork rows={shipped} />
              {review.visibility ? <VisibilityPanel visibility={review.visibility} prior={prior} href={`/${client.slug}/llm`} /> : null}
            </>
          ) : null}
        </div>


      </div>
    </section>
  );
}
