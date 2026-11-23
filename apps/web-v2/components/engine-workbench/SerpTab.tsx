"use client";

import { useState } from "react";

import type { ActionContext, SerpLookupResult } from "@/lib/engine";
import { formatDay, Pill } from "@/components/engine-workbench/tokens";

const SELLING = new Set(["product page", "category or collection page", "service page", "local listing"]);
const EXPLAINING = new Set(["article or blog post", "guide or resource"]);

export function SerpTab({
  defaultSearch,
  activeSearch,
  serp,
  loading,
  pulling,
  error,
  intent,
  onLookup,
  onPull,
}: {
  defaultSearch: string;
  activeSearch: string;
  serp: SerpLookupResult | null;
  loading: boolean;
  pulling: boolean;
  error: string | null;
  intent: ActionContext["intent"] | undefined;
  onLookup: (search: string) => void;
  onPull: (search: string) => void;
}) {
  const [customQuery, setCustomQuery] = useState("");
  const rankedIntent = intent?.ranked ?? [];
  const queryShown = serp?.search || activeSearch || defaultSearch;

  const featureList = Array.from(
    new Set([
      ...(serp?.item_types ?? []),
      ...(serp?.features ?? []),
      ...(intent?.features ?? []),
    ]),
  ).filter((f) => f && f !== "organic");

  const holderEntries = Object.entries(serp?.holders ?? {}).filter(([, list]) => list.length > 0);
  const questions = serp?.questions ?? [];
  const results = serp?.results ?? [];

  // Map ranked intent metadata by rank or URL for rich pairing alongside DataForSEO results.
  const intentByUrl = new Map(rankedIntent.map((r) => [r.url, r]));
  const intentByRank = new Map(rankedIntent.map((r) => [r.rank, r]));

  return (
    <div className="space-y-3.5">
      {/* Query bar + Pull live SERP */}
      <div className="rounded-xl border border-[#ececec] bg-white px-4 py-3.5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
              DataForSEO results page
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-2">
              <span className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">
                “{queryShown}”
              </span>
              {serp?.pulled_on ? (
                <Pill t="ok">Pulled {formatDay(serp.pulled_on, true)}</Pill>
              ) : (
                <Pill t="warn">Not pulled yet</Pill>
              )}
              {serp && !serp.configured ? (
                <Pill t="miss">DataForSEO not configured</Pill>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {queryShown !== defaultSearch ? (
              <button
                type="button"
                onClick={() => onLookup(defaultSearch)}
                className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3 py-1.5 text-xs font-semibold text-[#4a5560] hover:bg-[#f6f7f7]"
              >
                Reset to “{defaultSearch}”
              </button>
            ) : null}
            <button
              type="button"
              disabled={pulling || (serp != null && !serp.configured)}
              onClick={() => onPull(queryShown)}
              title={
                serp && !serp.configured
                  ? "Configure DataForSEO credentials to pull live SERP data."
                  : "Fetch live DataForSEO SERP features, People Also Ask, and top results"
              }
              className="cursor-pointer rounded-full bg-[#223540] px-4 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-45"
            >
              {pulling ? "Pulling live SERP…" : "Pull live SERP"}
            </button>
          </div>
        </div>

        {/* Inspect or pull any untracked query */}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const q = customQuery.trim();
            if (q) onLookup(q);
          }}
          className="mt-3 flex flex-wrap items-center gap-2 border-t border-[#f1f2f3] pt-3"
        >
          <input
            type="search"
            value={customQuery}
            onChange={(e) => setCustomQuery(e.target.value)}
            placeholder="Inspect another or untracked search query…"
            aria-label="Inspect another or untracked search query"
            className="min-w-[14rem] flex-1 rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-1.5 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
          />
          <button
            type="submit"
            disabled={!customQuery.trim() || loading}
            className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3.5 py-1.5 text-xs font-semibold text-[#223540] hover:bg-[#f6f7f7] disabled:opacity-50"
          >
            Look up
          </button>
          <button
            type="button"
            disabled={!customQuery.trim() || pulling || (serp != null && !serp.configured)}
            onClick={() => {
              const q = customQuery.trim();
              if (q) onPull(q);
            }}
            className="cursor-pointer rounded-full bg-[#00a99d] px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-[#008077] disabled:opacity-50"
          >
            Pull untracked SERP
          </button>
        </form>
      </div>

      {error ? (
        <p role="alert" className="rounded-xl border border-[oklch(0.88_0.06_25)] bg-white px-4 py-3 text-[13px] text-[oklch(0.48_0.17_25)]">
          {error}
        </p>
      ) : null}

      {serp && !serp.configured ? (
        <div className="rounded-xl border border-dashed border-[oklch(0.82_0.08_25)] bg-white px-4 py-3 text-[13px] text-[#4a5560]">
          <strong className="text-[#0a0c0f]">DataForSEO is not configured on this install.</strong> Stored SERP results (if any) are shown below, and live SERP pulls are disabled until DataForSEO credentials are set.
        </div>
      ) : null}

      {loading && !serp ? (
        <div className="rounded-xl border border-[#ececec] bg-white px-4 py-4 text-[13px] text-[#4a5560]">
          Loading stored SERP details…
        </div>
      ) : null}

      {/* Features & Holders */}
      {(featureList.length > 0 || holderEntries.length > 0) ? (
        <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            SERP features &amp; holders
          </div>
          {featureList.length > 0 ? (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {featureList.map((f) => (
                <Pill key={f} t="info">{f.replaceAll("_", " ")}</Pill>
              ))}
            </div>
          ) : null}
          {holderEntries.length > 0 ? (
            <dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {holderEntries.map(([feature, list]) => (
                <div key={feature} className="rounded-[10px] border border-[#f1f2f3] bg-[#f8f8f8] px-3 py-2">
                  <dt className="text-[11px] font-bold uppercase tracking-wide text-[#7a838c]">
                    {feature.replaceAll("_", " ")}
                  </dt>
                  <dd className="mt-1 text-xs font-medium text-[#171a22]">
                    {list.join(", ")}
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}

      {/* People Also Ask */}
      {questions.length > 0 ? (
        <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
              People also ask on this SERP ({questions.length})
            </span>
          </div>
          <ul className="mt-2 space-y-1.5 text-[13px] text-[#171a22]">
            {questions.map((q) => (
              <li key={q} className="flex items-start gap-2">
                <span className="font-bold text-[#00a99d]">?</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* Full Results List */}
      {results.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-[#ececec] bg-white">
          <div className="flex items-center justify-between border-b border-[#f1f2f3] px-4 py-3">
            <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
              Organic results ({results.length})
            </span>
            {serp?.labels && serp.labels.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {serp.labels.map((l) => (
                  <Pill key={l} t="info">{l}</Pill>
                ))}
              </div>
            ) : null}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="text-[11px] uppercase tracking-wide text-[#7a838c]">
                <tr>
                  <th className="px-4 py-2 font-semibold">Rank</th>
                  <th className="px-4 py-2 font-semibold">Result</th>
                  <th className="px-4 py-2 font-semibold">Type</th>
                  <th className="px-4 py-2 font-semibold">Signal</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r) => {
                  const matched = intentByUrl.get(r.url) ?? intentByRank.get(r.rank);
                  const contentType = matched?.content_type ?? null;
                  return (
                    <tr key={`${r.rank}-${r.url}`} className="border-t border-[#f1f2f3] align-top">
                      <td className="px-4 py-2.5 font-semibold tabular-nums text-[#0a0c0f]">#{r.rank}</td>
                      <td className="px-4 py-2.5">
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-semibold text-[#0a0c0f] hover:text-[#00857b] hover:underline"
                        >
                          {r.title || r.domain}
                        </a>
                        <div className="text-[11px] text-[#7a838c]">{r.domain}</div>
                        {r.snippet ? (
                          <p className="mt-1 text-xs text-[#4a5560]">{r.snippet}</p>
                        ) : null}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-[#4a5560]">
                        {contentType ?? "—"}
                      </td>
                      <td className="px-4 py-2.5">
                        {SELLING.has(contentType ?? "") ? (
                          <Pill t="lime">Buying</Pill>
                        ) : EXPLAINING.has(contentType ?? "") ? (
                          <Pill t="info">Researching</Pill>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : rankedIntent.length > 0 ? (
        <div className="overflow-hidden rounded-xl border border-[#ececec] bg-white">
          <div className="border-b border-[#f1f2f3] px-4 py-3 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            Ranked results from intent reading ({rankedIntent.length})
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <thead className="text-[11px] uppercase tracking-wide text-[#7a838c]">
                <tr>
                  <th className="px-4 py-2 font-semibold">Rank</th>
                  <th className="px-4 py-2 font-semibold">Result</th>
                  <th className="px-4 py-2 font-semibold">Type</th>
                  <th className="px-4 py-2 font-semibold">Signal</th>
                </tr>
              </thead>
              <tbody>
                {rankedIntent.map((r) => (
                  <tr key={`${r.rank}-${r.url}`} className="border-t border-[#f1f2f3]">
                    <td className="px-4 py-2 tabular-nums">#{r.rank}</td>
                    <td className="px-4 py-2">
                      <span className="font-semibold">{r.title || r.domain}</span>
                      <span className="block text-[11px] text-[#7a838c]">{r.domain}</span>
                    </td>
                    <td className="px-4 py-2 text-[#4a5560]">{r.content_type ?? "Not established"}</td>
                    <td className="px-4 py-2">
                      {SELLING.has(r.content_type ?? "") ? (
                        <Pill t="lime">Buying</Pill>
                      ) : EXPLAINING.has(r.content_type ?? "") ? (
                        <Pill t="info">Researching</Pill>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : !loading ? (
        <div className="rounded-xl border border-dashed border-[oklch(0.82_0.08_25)] bg-white px-4 py-4 text-[13px] text-[#4a5560]">
          <p className="font-semibold text-[#0a0c0f]">
            No stored results page for “{queryShown}”.
          </p>
          <p className="mt-1">
            {intent?.uncertainty
              ? intent.uncertainty
              : "Pull the live SERP above to fetch organic rankings, SERP feature holders, and People Also Ask questions."}
          </p>
        </div>
      ) : null}
    </div>
  );
}
