"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useState } from "react";

import type { SummaryRow, SummarySection } from "@/lib/review";

const KEY = "oiq-review-summary-open";
const TONE = { good: "bg-[#e7fedc] text-[#2f6b0d]", bad: "bg-[#fde8e4] text-[#b23a15]", flat: "bg-[#eceef2] text-[#4a5468]" } as const;
const ARROW = { good: "▲", bad: "▼", flat: "•" } as const;

/** One line of the summary: what it is (with its detail under it), the figure, and how it moved, each in its own column so the figures and chips line up down the page. A long value (a list of platforms) goes under the label instead. */
function Row({ row }: { row: SummaryRow }) {
  const long = row.value.length > 16;
  const chip = row.change ? (
    <span className={`inline-block whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${TONE[row.change.tone]}`}>
      {ARROW[row.change.tone]} {row.change.text}
    </span>
  ) : null;
  const notes = (
    <>
      {row.change ? <p className="text-xs text-[var(--text-tertiary)]">{row.change.against}</p> : null}
      {row.detail ? <p className="text-xs leading-snug text-[var(--text-secondary)]">{row.detail}</p> : null}
    </>
  );
  if (long) {
    return (
      <div className="border-t border-[var(--border)] py-3 first:border-t-0">
        <div className="text-sm font-medium">{row.label}</div>
        <div className="mt-0.5 text-sm font-semibold leading-snug">{row.value}</div>
        {notes}
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_7rem] items-start gap-x-3 border-t border-[var(--border)] py-3 first:border-t-0">
      <div className="min-w-0">
        <div className="text-sm font-medium">{row.label}</div>
        {notes}
      </div>
      <div className="text-right font-[family-name:var(--font-heading)] text-lg font-bold leading-tight tabular-nums">{row.value}</div>
      <div className="pt-0.5 text-right">{chip}</div>
    </div>
  );
}

/**
 * The full written summary, which the scorecards above now say at a glance. It folds away (and stays folded or open as the person left it),
 * and Copy is always in reach, so the text can still be pasted into an email without opening it.
 */
export function ReviewSummary({ lines, sections }: { lines: string[]; sections: SummarySection[] }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    try {
      setOpen(localStorage.getItem(KEY) === "1");
    } catch {
      /* folded until opened */
    }
  }, []);
  const toggle = () => {
    const next = !open;
    setOpen(next);
    try {
      localStorage.setItem(KEY, next ? "1" : "0");
    } catch {
      /* kept for this visit only */
    }
  };

  return (
    <section aria-label="Full summary" className="@container rounded-2xl border border-[var(--border)] bg-white">
      <div className="flex items-center gap-3 px-5 py-3">
        <button type="button" onClick={toggle} aria-expanded={open} aria-controls="review-summary-body" className="flex flex-1 items-center gap-2 text-left">
          <ChevronDown size={16} className={`shrink-0 text-[var(--text-secondary)] transition-transform ${open ? "" : "-rotate-90"}`} aria-hidden />
          <span className="text-sm font-bold">Full summary</span>
          <span className="text-xs text-[var(--text-tertiary)]">{open ? "Hide" : `Show every figure behind the cards (${sections.reduce((n, s) => n + s.rows.length, 0)})`}</span>
        </button>
        <button
          type="button"
          onClick={async () => {
            await navigator.clipboard.writeText(lines.join("\n"));
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
          className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--background)]"
        >
          {copied ? "Copied" : "Copy text"}
        </button>
      </div>
      {open ? (
        <div id="review-summary-body" className="border-t border-[var(--border)] px-5 pb-4 pt-3">
          <div className="grid gap-x-8 gap-y-4 @2xl:grid-cols-2">
            {sections.map((section) => (
              <div key={section.title} className={`min-w-0 ${section.rows.length > 3 ? "@2xl:col-span-2" : ""}`}>
                <h3 className="border-b border-[var(--border)] pb-1.5 text-[0.7rem] font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{section.title}</h3>
                <div className={section.rows.length > 3 ? "@2xl:grid @2xl:grid-cols-2 @2xl:gap-x-8" : ""}>{section.rows.map((row) => <Row key={row.label} row={row} />)}</div>
              </div>
            ))}
          </div>
          <p className="mt-3 text-xs text-[var(--text-tertiary)]">Worked out from the numbers below. It says what moved, not why.</p>
        </div>
      ) : null}
    </section>
  );
}
