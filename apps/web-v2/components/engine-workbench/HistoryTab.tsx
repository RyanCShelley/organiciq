"use client";

import type { PageHistory } from "@/lib/engine";
import { formatDay, num, Pill, type Tone } from "@/components/engine-workbench/tokens";

const TASK_TONE: Record<string, Tone> = {
  shipped: "lime",
  sent: "ok",
  confirmed: "info",
  rejected: "miss",
  dropped: "warn",
};

export function HistoryTab({
  history,
  loading,
  error,
  onRefresh,
}: {
  history: PageHistory | null | undefined;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
}) {
  if (loading && !history) {
    return (
      <div className="rounded-xl border border-[#ececec] bg-white p-5 text-[13px] text-[#4a5560]">
        Loading page edit &amp; action history…
      </div>
    );
  }

  if (error && !history) {
    return (
      <div className="rounded-xl border border-[oklch(0.88_0.06_25)] bg-white p-4 text-[13px] text-[oklch(0.48_0.17_25)]">
        <p>{error}</p>
        <button
          type="button"
          onClick={onRefresh}
          className="mt-2 cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3 py-1 text-xs font-semibold text-[#223540] hover:bg-[#f6f7f7]"
        >
          Try again
        </button>
      </div>
    );
  }

  const crawls = history?.crawl_changes ?? [];
  const tasks = history?.tasks ?? [];
  const annotations = history?.annotations ?? [];

  return (
    <div className="space-y-3.5">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#ececec] bg-white px-4 py-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            Page history &amp; audit trail
          </div>
          <p className="mt-0.5 text-[13px] text-[#4a5560]">
            {crawls.length} crawl snapshot{crawls.length === 1 ? "" : "s"} · {tasks.length} engine task{tasks.length === 1 ? "" : "s"} · {annotations.length} annotation{annotations.length === 1 ? "" : "s"}
          </p>
        </div>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-3 py-1 text-xs font-semibold text-[#223540] hover:bg-[#f6f7f7] disabled:opacity-50"
        >
          {loading ? "Refreshing…" : "Refresh history"}
        </button>
      </div>

      {/* Past Decision Engine Tasks */}
      <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          Decision Engine task history
        </div>
        {tasks.length === 0 ? (
          <p className="mt-2 text-[13px] text-[#7a838c]">
            No past Decision Engine tasks recorded for this page yet.
          </p>
        ) : (
          <ul className="mt-2.5 divide-y divide-[#f1f2f3]">
            {tasks.map((t) => {
              const tone = TASK_TONE[t.status] ?? "info";
              return (
                <li key={t.id} className="py-3 first:pt-1 last:pb-1">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Pill t={tone}>{t.status}</Pill>
                        <span className="text-xs font-semibold text-[#0a0c0f]">{t.title}</span>
                      </div>
                      <div className="mt-1 text-xs text-[#4a5560]">
                        Search: “{t.search}” · Month: {t.month}
                        {t.confirmed_at ? ` · Confirmed ${formatDay(t.confirmed_at, true)}` : ""}
                        {t.shipped_at ? ` · Shipped ${formatDay(t.shipped_at, true)}` : ""}
                      </div>
                    </div>
                  </div>
                  {t.parts.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {t.parts.map((p, idx) => (
                        <Pill key={`${t.id}-p-${idx}`} t={p.status === "done" ? "ok" : "info"}>
                          {p.name}{p.status === "done" ? " ✓" : ""}
                        </Pill>
                      ))}
                    </div>
                  ) : null}
                  {t.status === "rejected" || t.rejection_reason ? (
                    <div className="mt-2 rounded-[10px] border border-[oklch(0.88_0.06_25)] bg-[oklch(0.965_0.025_25)] px-3 py-2 text-xs text-[oklch(0.48_0.17_25)]">
                      <strong>{t.rejection_reason_label ?? t.rejection_reason ?? "Rejected"}</strong>
                      {t.rejected_at ? ` · ${formatDay(t.rejected_at, true)}` : ""}
                      {t.rejected_by ? ` by ${t.rejected_by.split("@")[0]}` : ""}
                      {t.rejection_note ? <p className="mt-0.5 text-[#171a22]">{t.rejection_note}</p> : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Crawl Content Diffs */}
      <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          Crawl snapshots &amp; content diffs
        </div>
        {crawls.length === 0 ? (
          <p className="mt-2 text-[13px] text-[#7a838c]">
            No crawl snapshots stored for this page yet.
          </p>
        ) : (
          <ul className="mt-2.5 divide-y divide-[#f1f2f3]">
            {crawls.map((c, idx) => (
              <li key={`${c.snapshot_date}-${idx}`} className="py-3 first:pt-1 last:pb-1 text-[13px]">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="font-semibold text-[#0a0c0f]">
                      Crawl of {formatDay(c.snapshot_date, true)}
                    </span>
                    {c.content_changed_on ? (
                      <Pill t="ok">Changed {formatDay(c.content_changed_on)}</Pill>
                    ) : null}
                  </div>
                  <span className="text-xs text-[#7a838c] tabular-nums">
                    {c.word_count != null ? `${num(c.word_count)} words · ` : ""}
                    {c.paragraphs_count} paragraph{c.paragraphs_count === 1 ? "" : "s"}
                  </span>
                </div>
                {c.title ? (
                  <p className="mt-1 text-xs text-[#4a5560]">
                    <strong className="text-[#171a22]">Title:</strong> {c.title}
                  </p>
                ) : null}
                {c.meta_description ? (
                  <p className="mt-0.5 text-xs text-[#4a5560]">
                    <strong className="text-[#171a22]">Description:</strong> {c.meta_description}
                  </p>
                ) : null}
                {c.diff_summary ? (
                  <div className="mt-2 rounded-[10px] border border-[#eef0f1] bg-[#f8f8f8] px-3 py-2 text-xs">
                    <div className="font-semibold text-[#0a0c0f]">
                      Diff vs previous ({c.diff_summary.previous_count} → {c.diff_summary.current_count} paragraphs):{" "}
                      <span className="text-[#00857b]">+{c.diff_summary.added_count} added</span>
                      {" · "}
                      <span className="text-[oklch(0.48_0.17_25)]">−{c.diff_summary.removed_count} removed</span>
                    </div>
                    {c.diff_summary.added_samples.length > 0 ? (
                      <ul className="mt-1.5 space-y-1 text-[#00665f]">
                        {c.diff_summary.added_samples.map((s, si) => (
                          <li key={`add-${si}`} className="truncate">+ {s}</li>
                        ))}
                      </ul>
                    ) : null}
                    {c.diff_summary.removed_samples.length > 0 ? (
                      <ul className="mt-1 space-y-1 text-[oklch(0.48_0.17_25)]">
                        {c.diff_summary.removed_samples.map((s, si) => (
                          <li key={`rem-${si}`} className="truncate">− {s}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Annotations */}
      <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          Annotations &amp; shipped logs
        </div>
        {annotations.length === 0 ? (
          <p className="mt-2 text-[13px] text-[#7a838c]">
            No annotations logged for this page yet.
          </p>
        ) : (
          <ul className="mt-2.5 divide-y divide-[#f1f2f3]">
            {annotations.map((a) => (
              <li key={a.id} className="py-2.5 first:pt-1 last:pb-1 text-[13px]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-xs font-semibold text-[#7a838c] tabular-nums">{formatDay(a.date, true)}</span>
                  <Pill t="info">{a.annotation_type.replaceAll("_", " ")}</Pill>
                  {a.result ? (
                    <Pill t={a.result === "positive" ? "lime" : a.result === "negative" ? "miss" : "info"}>
                      {a.result}
                    </Pill>
                  ) : null}
                </div>
                <p className="mt-1 text-[#171a22]">{a.description}</p>
                {a.verified_how ? (
                  <p className="mt-0.5 text-xs text-[#00665f]">Verified: {a.verified_how}</p>
                ) : null}
                {a.notes ? (
                  <p className="mt-0.5 text-xs text-[#4a5560]">{a.notes}</p>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
