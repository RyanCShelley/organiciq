"use client";

import type { PageHistory } from "@/lib/engine";

const shortDate = (iso: string | null | undefined) => {
  if (!iso) return "";
  const d = new Date(iso.includes("T") ? iso : `${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
};

function taskStatusPill(status: string) {
  if (status === "rejected") {
    return "bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]";
  }
  if (status === "shipped") {
    return "bg-[#e9fedc] text-[#2f5a00]";
  }
  if (status === "sent" || status === "confirmed") {
    return "bg-[#e6f7f5] text-[#00665f]";
  }
  return "bg-[#f1f3f4] text-[#4a5560]";
}

export function PageHistoryPanel({ history }: { history: PageHistory | undefined | null }) {
  if (!history) return null;

  const total = history.crawl_changes.length + history.tasks.length + history.annotations.length;

  return (
    <details className="rounded-xl border border-[#ececec] bg-white p-4">
      <summary className="flex cursor-pointer flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          Page edit &amp; action history
        </span>
        <span className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold text-[#4a5560]">
          <span className="rounded-full bg-[#f1f3f4] px-2.5 py-0.5">
            {history.crawl_changes.length} crawl snapshot{history.crawl_changes.length === 1 ? "" : "s"}
          </span>
          <span className="rounded-full bg-[#f1f3f4] px-2.5 py-0.5">
            {history.tasks.length} task{history.tasks.length === 1 ? "" : "s"}
          </span>
          <span className="rounded-full bg-[#f1f3f4] px-2.5 py-0.5">
            {history.annotations.length} annotation{history.annotations.length === 1 ? "" : "s"}
          </span>
        </span>
      </summary>

      {total === 0 ? (
        <p className="mt-3 rounded-[10px] border border-dashed border-[#d3d7d9] bg-[#f8f8f8] px-3.5 py-2.5 text-xs text-[#7a838c]">
          No prior crawl content diffs, Decision Engine tasks, or annotations recorded for this page yet.
        </p>
      ) : (
        <div className="mt-3 space-y-4">
          {history.tasks.length > 0 ? (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                Decision Engine tasks ({history.tasks.length})
              </div>
              <ul className="mt-2 space-y-2">
                {history.tasks.map((t) => (
                  <li key={t.id} className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3 py-2.5 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-[#0a0c0f]">{t.title}</span>
                      <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${taskStatusPill(t.status)}`}>
                        {t.status}
                      </span>
                    </div>
                    <div className="mt-1 text-[#4a5560]">
                      {t.month} · “{t.search}”
                      {t.confirmed_by ? ` · confirmed by ${t.confirmed_by}` : ""}
                      {t.shipped_at ? ` · shipped ${shortDate(t.shipped_at)}` : ""}
                    </div>
                    {t.status === "rejected" && (t.rejection_reason_label || t.rejection_reason || t.rejection_note) ? (
                      <div className="mt-1.5 rounded-lg border border-[oklch(0.88_0.06_25)] bg-white px-2.5 py-1.5 text-[oklch(0.48_0.17_25)]">
                        <strong>Reason:</strong> {t.rejection_reason_label ?? t.rejection_reason}
                        {t.rejection_note ? ` — ${t.rejection_note}` : ""}
                        {t.rejected_by ? ` (${t.rejected_by}${t.rejected_at ? `, ${shortDate(t.rejected_at)}` : ""})` : ""}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {history.crawl_changes.length > 0 ? (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                Crawl snapshots &amp; content diffs ({history.crawl_changes.length})
              </div>
              <ul className="mt-2 space-y-2">
                {history.crawl_changes.map((c, idx) => (
                  <li key={`${c.snapshot_date}-${idx}`} className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3 py-2.5 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-[#0a0c0f]">Crawl {shortDate(c.snapshot_date)}</span>
                      <span className="text-[#4a5560] tabular-nums">
                        {c.word_count != null ? `${c.word_count.toLocaleString()} words · ` : ""}
                        {c.paragraphs_count} paragraphs
                      </span>
                    </div>
                    {c.content_changed_on || c.content_updated_on ? (
                      <div className="mt-0.5 text-[#4a5560]">
                        {c.content_changed_on ? `Content changed ${shortDate(c.content_changed_on)}` : ""}
                        {c.content_changed_on && c.content_updated_on ? " · " : ""}
                        {c.content_updated_on ? `Updated ${shortDate(c.content_updated_on)}` : ""}
                      </div>
                    ) : null}
                    {c.diff_summary ? (
                      <div className="mt-1.5 space-y-1 text-[#171a22]">
                        <div className="flex flex-wrap gap-1.5">
                          <span className="rounded-full bg-[#e6f7f5] px-2 py-0.5 text-[10px] font-semibold text-[#00665f]">
                            +{c.diff_summary.added_count} added
                          </span>
                          <span className="rounded-full bg-[oklch(0.965_0.025_25)] px-2 py-0.5 text-[10px] font-semibold text-[oklch(0.48_0.17_25)]">
                            -{c.diff_summary.removed_count} removed
                          </span>
                          <span className="text-[11px] text-[#7a838c]">
                            ({c.diff_summary.previous_count} → {c.diff_summary.current_count} blocks)
                          </span>
                        </div>
                        {c.diff_summary.added_samples.length > 0 ? (
                          <div className="text-[11px] text-[#4a5560]">
                            <strong className="text-[#00665f]">Added:</strong> {c.diff_summary.added_samples.join(" | ")}
                          </div>
                        ) : null}
                        {c.diff_summary.removed_samples.length > 0 ? (
                          <div className="text-[11px] text-[#4a5560]">
                            <strong className="text-[oklch(0.48_0.17_25)]">Removed:</strong> {c.diff_summary.removed_samples.join(" | ")}
                          </div>
                        ) : null}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {history.annotations.length > 0 ? (
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                Annotations ({history.annotations.length})
              </div>
              <ul className="mt-2 space-y-2">
                {history.annotations.map((a) => (
                  <li key={a.id} className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3 py-2.5 text-xs">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="font-semibold text-[#0a0c0f]">
                        {shortDate(a.date)} · {a.annotation_type.replaceAll("_", " ")}
                      </span>
                      {a.result ? (
                        <span className="rounded-full bg-[#e6f7f5] px-2 py-0.5 text-[10px] font-semibold text-[#00665f]">
                          {a.result}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-[#171a22]">{a.description}</p>
                    {a.verified_how ? <p className="mt-0.5 text-[#4a5560]">Verified: {a.verified_how}</p> : null}
                    {a.notes ? <p className="mt-0.5 text-[#7a838c]">{a.notes}</p> : null}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
    </details>
  );
}
