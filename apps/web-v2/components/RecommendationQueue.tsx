"use client";

import Link from "next/link";

import { Kpi, card } from "@/components/content/parts";
import type { Client } from "@/lib/api";
import { CATEGORY_LABEL, FOCUS_LABEL, IMPL_LABEL, STATE_LABEL, type RecList, type RecState } from "@/lib/portal";

const STATES: RecState[] = ["draft", "under_review", "approved", "published", "archived"];
const PRIORITY_CLS = { high: "bg-red-50 text-red-800", medium: "bg-amber-50 text-amber-900", low: "bg-[var(--bg)] text-[var(--text-secondary)]" } as const;

/** The consultant's briefs for one client, by where they are in review. */
export function RecommendationQueue({ client, data, error, state }: { client: Client; data: RecList | null; error: string | null; state: string | null }) {
  const base = `/${client.slug}/consulting/recommendations`;
  return (
    <section className="max-w-5xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Recommendations</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.client_name}. Briefs for their team. Only a published brief appears in the client portal, and publishing creates no work for SMA.</p>
        </div>
        <Link href={`${base}/new`} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white">Add one by hand</Link>
      </header>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {data ? (
        <>
          {data.follow_ups > 0 ? (
            <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><span className="font-semibold">{data.follow_ups} published brief{data.follow_ups === 1 ? "" : "s"} with no update from the client</span> after two weeks. Open one and record a follow-up or what you heard.</p>
          ) : null}
          <div className="flex flex-wrap gap-2 text-sm">
            <Link href={base} className={`rounded-full border px-3 py-1 font-semibold ${!state ? "border-[var(--brand-dark)] bg-[var(--brand-dark)] text-white" : "border-[var(--border)] bg-white"}`}>All</Link>
            {STATES.map((s) => (
              <Link key={s} href={`${base}?state=${s}`} className={`rounded-full border px-3 py-1 font-semibold ${state === s ? "border-[var(--brand-dark)] bg-[var(--brand-dark)] text-white" : "border-[var(--border)] bg-white"}`}>{STATE_LABEL[s]} {data.counts[s]}</Link>
            ))}
          </div>
          <section className={`${card} px-5`}>
            {data.recommendations.length === 0 ? (
              <p className="py-4 text-sm text-[var(--text-secondary)]">Nothing here yet. Add a brief by hand; drafting from the engine, site health and GEO findings is coming next.</p>
            ) : (
              <ul className="divide-y divide-[var(--border)]">
                {data.recommendations.map((r) => (
                  <li key={r.id} className="py-3">
                    <Link href={`${base}/${r.id}`} className="block hover:bg-[var(--bg)]">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="rounded-full bg-[var(--bg)] px-2 py-0.5 font-semibold">{CATEGORY_LABEL[r.category]}</span>
                        <span className="rounded-full bg-[var(--bg)] px-2 py-0.5">{FOCUS_LABEL[r.focus]}</span>
                        <span className={`rounded-full px-2 py-0.5 font-semibold ${PRIORITY_CLS[r.priority]}`}>{r.priority[0].toUpperCase() + r.priority.slice(1)} priority</span>
                        <span className="text-[var(--text-tertiary)]">{r.source_kind.replace("_", " ")}</span>
                      </div>
                      <div className="mt-1 font-semibold">{r.title}</div>
                      <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                        {STATE_LABEL[r.review_state]}
                        {r.review_state === "published" ? ` · ${IMPL_LABEL[r.impl_status]}${r.impl_status_source ? ` (${r.impl_status_source.replace("_", " ")})` : " (not reported)"}${r.verification === "verified" ? " · verified" : ""}` : ""}
                      </div>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <div className="grid gap-3 sm:grid-cols-3">
            <Kpi label="Published" value={String(data.counts.published)} note="visible to the client" />
            <Kpi label="In review" value={String(data.counts.draft + data.counts.under_review + data.counts.approved)} note="draft, under review or approved" />
            <Kpi label="Chase up" value={String(data.follow_ups)} note="no update after two weeks" />
          </div>
        </>
      ) : null}
    </section>
  );
}
