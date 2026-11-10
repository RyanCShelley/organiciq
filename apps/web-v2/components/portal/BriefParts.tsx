import { CATEGORY_LABEL, FOCUS_LABEL, IMPL_LABEL, type ClientRec } from "@/lib/portal";

export const PRIORITY = { high: { label: "High priority", cls: "bg-red-50 text-red-800" }, medium: { label: "Medium priority", cls: "bg-amber-50 text-amber-900" }, low: { label: "Lower priority", cls: "bg-[var(--bg)] text-[var(--text-secondary)]" } } as const;
export const card = "rounded-xl border border-[var(--border)] bg-white";

/** Where a brief stands. We often do not know, so "not reported" is said plainly instead of being read as "not done". */
export function StatusLine({ rec }: { rec: ClientRec }) {
  const tone = rec.impl_status === "completed" ? "text-green-800" : rec.impl_status === "blocked" ? "text-red-800" : "text-[var(--text-secondary)]";
  return (
    <span className={`text-xs font-semibold ${tone}`}>
      {IMPL_LABEL[rec.impl_status]}
      {rec.reported ? "" : " · not reported yet"}
      {rec.verification === "verified" ? " · ✓ confirmed on the live page" : ""}
    </span>
  );
}

export function Chips({ rec }: { rec: ClientRec }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <span className="rounded-full bg-[var(--bg-accent,#e6f1fb)] px-2 py-0.5 font-semibold text-[var(--brand-teal)]">{CATEGORY_LABEL[rec.category]}</span>
      {rec.focus !== "seo" ? <span className="rounded-full bg-[var(--bg)] px-2 py-0.5">{FOCUS_LABEL[rec.focus]}</span> : null}
      <span className={`rounded-full px-2 py-0.5 font-semibold ${PRIORITY[rec.priority].cls}`}>{PRIORITY[rec.priority].label}</span>
    </div>
  );
}
