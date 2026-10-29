"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState, useTransition } from "react";

import type { Client } from "@/lib/api";
import { saveFocusAction } from "@/app/(app)/[clientSlug]/focus/actions";
import type { Candidate, EngineOverview, VisibilityCandidates } from "@/lib/engine";
import { FOCUSES, monthLabel, type ClientFocus } from "@/lib/focus";

const num = (n: number | null | undefined, digits = 0) =>
  n == null ? "–" : n.toLocaleString(undefined, { maximumFractionDigits: digits });

function shortPage(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

function Moved({ places }: { places: number | null }) {
  if (places == null || Math.abs(places) < 0.5) return null;
  return (
    <span className={`ml-1 text-xs ${places > 0 ? "text-green-700" : "text-red-700"}`}>
      {places > 0 ? "▲" : "▼"}
      {Math.abs(places).toFixed(1)}
    </span>
  );
}

function Row({ c }: { c: Candidate }) {
  return (
    <tr className="border-t border-[var(--border)] align-top">
      <td className="min-w-[10rem] py-2 pr-3">
        <div className="font-medium">{c.search}</div>
        <div className="mt-0.5 max-w-[20rem] truncate text-xs text-[var(--text-secondary)]" title={c.page}>
          {shortPage(c.page)}
          {c.pages_for_search > 1 ? (
            <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-amber-800">
              {c.pages_for_search} pages rank for this
            </span>
          ) : null}
        </div>
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {num(c.position, 1)}
        <Moved places={c.position_change} />
        <div className="text-xs text-[var(--text-tertiary)]">aim {c.target_position}</div>
      </td>
      <td className="px-3 py-2 text-right tabular-nums">
        {num(c.impressions)}
        {c.impressions_change_pct != null && Math.abs(c.impressions_change_pct) >= 1 ? (
          <span className={`ml-1 text-xs ${c.impressions_change_pct > 0 ? "text-green-700" : "text-red-700"}`}>
            {c.impressions_change_pct > 0 ? "▲" : "▼"}
            {Math.abs(c.impressions_change_pct).toFixed(0)}%
          </span>
        ) : null}
      </td>
      <td className="px-3 py-2 text-right tabular-nums">{num(c.clicks)}</td>
      <td className="px-3 py-2 text-right font-semibold tabular-nums">+{num(c.expected_extra_clicks, 1)}</td>
      <td className="py-2 pl-3">
        <span
          className={`whitespace-nowrap rounded px-2 py-0.5 text-xs font-semibold ${
            c.strength === "strong" ? "bg-green-50 text-green-800" : "bg-[var(--bg)] text-[var(--text-secondary)]"
          }`}
        >
          {c.strength}
        </span>
        {c.reason ? <div className="mt-0.5 text-xs text-[var(--text-tertiary)]">{c.reason}</div> : null}
      </td>
    </tr>
  );
}

export function EngineScreen({
  client,
  workMonth,
  focus,
  buckets,
  bucketId,
  showVisibility,
  data,
  overview,
  error,
}: {
  client: Client;
  workMonth: string;
  focus: ClientFocus | null;
  buckets: { id: string; name: string }[];
  bucketId: string | null;
  showVisibility: boolean;
  data: VisibilityCandidates | null;
  overview: EngineOverview;
  error: string | null;
}) {
  const router = useRouter();
  const [band, setBand] = useState<string | null>(null);
  const [switching, startSwitch] = useTransition();
  const [switchError, setSwitchError] = useState<string | null>(null);
  const advice = overview.advice;
  const buckets_ = overview.buckets;

  function switchTo(bucketId: string) {
    setSwitchError(null);
    startSwitch(async () => {
      const result = await saveFocusAction(client.id, client.slug, workMonth, "visibility", bucketId);
      if (result.ok) router.push(`/${client.slug}/engine`);
      else setSwitchError(result.error);
    });
  }
  const focusLabel = FOCUSES.find((f) => f.value === focus?.focus)?.label;

  const shown = useMemo(
    () => (data ? data.candidates.filter((c) => band === null || c.band === band) : []),
    [data, band],
  );

  return (
    <section className="max-w-6xl">
      <header className="mb-6">
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">Decision engine</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.client_name}</p>
      </header>

      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4 text-sm">
        {focus ? (
          <span>
            Focus for <strong>{monthLabel(workMonth)}</strong>: <strong>{focusLabel}</strong>
            {focus.bucket_name ? <> · {focus.bucket_name}</> : " · no bucket chosen"}
          </span>
        ) : (
          <span>
            No focus is set for <strong>{monthLabel(workMonth)}</strong>.
          </span>
        )}
        <Link href={`/${client.slug}/review`} className="font-semibold text-[var(--brand-teal)] hover:underline">
          {focus ? "Change on the monthly review →" : "Choose it on the monthly review →"}
        </Link>
      </div>

      {advice.level !== "ok" && advice.headline ? (
        <div
          className={`mb-6 rounded-xl border p-5 text-sm ${
            advice.level === "thin_data" ? "border-red-200 bg-red-50 text-red-900" : "border-amber-200 bg-amber-50 text-amber-900"
          }`}
        >
          <h2 className="font-semibold">{advice.headline}</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {advice.reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
          {advice.suggestions.length > 0 ? (
            <div className="mt-3 space-y-2">
              <div className="text-xs font-semibold uppercase tracking-wide opacity-70">What you could do</div>
              {advice.suggestions.map((s) => (
                <div key={s.text} className="flex flex-wrap items-center justify-between gap-3">
                  <span>{s.text}</span>
                  {s.kind === "bucket" && s.bucket_id ? (
                    <button
                      type="button"
                      disabled={switching}
                      onClick={() => switchTo(s.bucket_id as string)}
                      className="rounded-lg bg-[var(--brand-teal)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Switch the focus to {s.name}
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : null}
          {switchError ? <p role="alert" className="mt-3 text-red-800">{switchError}</p> : null}
        </div>
      ) : null}

      {!showVisibility ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] p-6 text-sm text-[var(--text-secondary)]">
          {focus
            ? `Candidate lists for ${focusLabel} are the next thing to build. Visibility is ready now.`
            : "Set a focus and the candidates for it appear here. Visibility is ready now."}
          <div className="mt-3">
            <Link
              href={`/${client.slug}/engine?show=visibility`}
              className="font-semibold text-[var(--brand-teal)] hover:underline"
            >
              Show the Visibility candidates →
            </Link>
          </div>
        </div>
      ) : null}

      {buckets_.length > 0 ? (
        <div className="mb-6 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
          <h2 className="text-sm font-semibold">What each bucket has to move</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Searches where a page already ranks 2 to 20. A bucket with nothing here needs pages built for its terms
            before there is anything to move.
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                <tr>
                  <th className="py-1 pr-3 font-medium">Bucket</th>
                  <th className="px-3 py-1 text-right font-medium">Searches in reach</th>
                  <th className="px-3 py-1 text-right font-medium">Strong</th>
                  <th className="px-3 py-1 text-right font-medium">Extra clicks (top 20)</th>
                  <th className="py-1 pl-3 text-right font-medium">Terms with no impressions</th>
                </tr>
              </thead>
              <tbody>
                {buckets_.map((b) => (
                  <tr
                    key={b.id}
                    onClick={() => router.push(`/${client.slug}/engine?bucket=${b.id}${focus ? "" : "&show=visibility"}`)}
                    className={`cursor-pointer border-t border-[var(--border)] hover:bg-[var(--bg)] ${b.id === bucketId ? "bg-[var(--brand-teal)]/10 font-semibold" : ""}`}
                  >
                    <td className="py-2 pr-3">
                      {b.name}
                      {focus?.bucket_id === b.id ? (
                        <span className="ml-2 rounded bg-[var(--brand-teal)] px-1.5 py-0.5 text-xs font-semibold text-white">focus</span>
                      ) : null}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">{b.found.toLocaleString()}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{b.strong}</td>
                    <td className="px-3 py-2 text-right tabular-nums">+{num(b.expected_extra_clicks, 1)}</td>
                    <td className="py-2 pl-3 text-right tabular-nums">
                      {b.unranked_terms} of {b.terms}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {error ? (
        <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      {data ? (
        <div className="space-y-6">
          <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <div>
                <h2 className="text-sm font-semibold">Visibility candidates</h2>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  Searches where a page ranks 2 to 20 and a better position is worth chasing. Read over{" "}
                  {data.window.from} to {data.window.to}, against the three months before.
                </p>
              </div>
              <label className="text-sm">
                <span className="font-semibold">Scope</span>
                <select
                  value={bucketId ?? "site"}
                  onChange={(e) => router.push(`/${client.slug}/engine?bucket=${e.target.value}${showVisibility && !focus ? "&show=visibility" : ""}`)}
                  className="ml-2 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm"
                >
                  <option value="site">Whole site</option>
                  {buckets.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => setBand(null)}
                aria-pressed={band === null}
                className={`rounded-full border px-3 py-1 text-xs font-semibold ${band === null ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)]"}`}
              >
                All {data.counts.found.toLocaleString()}
              </button>
              {data.bands.map((b) => (
                <button
                  key={b.key}
                  type="button"
                  aria-pressed={band === b.key}
                  onClick={() => setBand(band === b.key ? null : b.key)}
                  className={`rounded-full border px-3 py-1 text-xs font-semibold ${band === b.key ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)]"}`}
                >
                  Rank {b.key}: {b.label.toLowerCase()} ({b.count.toLocaleString()})
                </button>
              ))}
              <span className="ml-auto text-xs text-[var(--text-secondary)]">
                {data.counts.strong} strong · {data.counts.possible.toLocaleString()} possible · top {data.counts.listed} listed
              </span>
            </div>

            {data.site_trend.impressions_change_pct != null ? (
              <p className="mt-3 text-xs text-[var(--text-secondary)]">
                For context, the whole site&apos;s impressions are {data.site_trend.impressions_change_pct > 0 ? "up" : "down"}{" "}
                {Math.abs(data.site_trend.impressions_change_pct).toFixed(0)}% and clicks{" "}
                {data.site_trend.clicks_change_pct != null && data.site_trend.clicks_change_pct > 0 ? "up" : "down"}{" "}
                {Math.abs(data.site_trend.clicks_change_pct ?? 0).toFixed(0)}% on the three months before, so judge a
                row&apos;s change against that.
              </p>
            ) : null}

            {data.bucket && data.bucket.id !== focus?.bucket_id && data.counts.strong === 0 && data.counts.found < 5 ? (
              <div className="mt-4 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">
                <strong>{data.bucket.name}</strong> has almost nothing to move: {data.counts.found}{" "}
                {data.counts.found === 1 ? "search" : "searches"} in reach, none strong
                {data.unranked.length > 0 ? `, and ${data.unranked.length} of its ${data.bucket.terms.length} terms have no Google impressions at all` : ""}.
                No page ranks well enough to nudge. These terms need a page written for them, which is content work
                and not a ranking fix.
                {buckets_.some((o) => o.id !== data.bucket?.id && o.strong > 0) ? (
                  <>
                    {" "}Buckets with real candidates: {buckets_.filter((o) => o.id !== data.bucket?.id && o.strong > 0).map((o) => `${o.name} (${o.strong} strong)`).join(", ")}.
                  </>
                ) : null}
              </div>
            ) : null}

            <div className="mt-4 overflow-x-auto">
              <table className="w-full min-w-[40rem] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                  <tr>
                    <th className="py-1 pr-3 font-medium">Search and page</th>
                    <th className="px-3 py-1 text-right font-medium">Position</th>
                    <th className="px-3 py-1 text-right font-medium">Impressions</th>
                    <th className="px-3 py-1 text-right font-medium">Clicks</th>
                    <th className="px-3 py-1 text-right font-medium">Extra clicks</th>
                    <th className="py-1 pl-3 font-medium">Strength</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.map((c) => (
                    <Row key={`${c.search}|${c.page}`} c={c} />
                  ))}
                </tbody>
              </table>
              {shown.length === 0 ? (
                <p className="py-4 text-sm text-[var(--text-tertiary)]">Nothing in this band for this scope.</p>
              ) : null}
            </div>
          </div>

          {data.unranked.length > 0 ? (
            <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
              <h2 className="text-sm font-semibold">Watchlist terms with no Google impressions</h2>
              <ul className="mt-3 divide-y divide-[var(--border)] text-sm">
                {data.unranked.map((u) => (
                  <li key={u.keyword} className="flex items-center justify-between gap-4 py-2">
                    <span className="font-medium">{u.keyword}</span>
                    <span className="text-[var(--text-secondary)]">{num(u.volume)} searches a month</span>
                    <span className="rounded bg-[var(--bg)] px-2 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">{u.strength}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-[var(--text-tertiary)]">{data.unranked[0].note}</p>
            </div>
          ) : null}

          <ul className="space-y-1 text-xs text-[var(--text-tertiary)]">
            {data.notes.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
