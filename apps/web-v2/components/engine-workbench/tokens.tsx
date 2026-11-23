"use client";

import Link from "next/link";
import { useState, type CSSProperties, type ReactNode } from "react";

import type { PriorRejection, RejectionReason } from "@/lib/engine";
import { REJECTION_REASONS } from "@/lib/engine";

export type Tone = "ok" | "warn" | "miss" | "info" | "lime";

export const TONE: Record<Tone, { bg: string; fg: string; dot: string; border: string }> = {
  ok: { bg: "#e6f7f5", fg: "#00665f", dot: "#00a99d", border: "#bfe9e4" },
  lime: { bg: "#e9fedc", fg: "#2f5a00", dot: "#aae437", border: "#c7efaa" },
  warn: { bg: "oklch(0.97 0.045 85)", fg: "oklch(0.42 0.1 65)", dot: "oklch(0.76 0.15 75)", border: "oklch(0.88 0.08 85)" },
  miss: { bg: "oklch(0.965 0.025 25)", fg: "oklch(0.48 0.17 25)", dot: "oklch(0.62 0.2 25)", border: "oklch(0.88 0.06 25)" },
  info: { bg: "#f1f3f4", fg: "#4a5560", dot: "#909a9f", border: "#e3e6e8" },
};

export const DARK = "#223540";
export const TEAL = "#00a99d";

export const toneStyle = (t: Tone): CSSProperties => ({
  background: TONE[t].bg,
  color: TONE[t].fg,
  borderColor: TONE[t].border,
});

export const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";

export const num = (n: number, digits = 0) => n.toLocaleString(undefined, { maximumFractionDigits: digits });

export function formatDay(iso: string | null | undefined, includeYear = false): string {
  if (!iso) return "";
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00`) : new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso.slice(0, 10);
  return parsed.toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    ...(includeYear ? { year: "numeric" } : {}),
  });
}

export function daysSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const parsed = /^\d{4}-\d{2}-\d{2}$/.test(iso) ? new Date(`${iso}T00:00:00`) : new Date(iso);
  if (Number.isNaN(parsed.getTime())) return null;
  return Math.floor((Date.now() - parsed.getTime()) / 86_400_000);
}

export function Pill({ t, children }: { t: Tone; children: ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-semibold leading-[16px]"
      style={toneStyle(t)}
    >
      {children}
    </span>
  );
}

export function StyleNotesBanner({
  styleNotes,
  clientSlug,
  compact = false,
}: {
  styleNotes: string | null | undefined;
  clientSlug: string;
  compact?: boolean;
}) {
  const clean = (styleNotes ?? "").trim();
  if (!clean) {
    return (
      <div
        className={`flex flex-wrap items-center justify-between gap-2 rounded-xl border border-dashed border-[#d3d7d9] bg-white ${
          compact ? "px-3.5 py-2.5" : "px-4 py-3"
        } text-xs text-[#4a5560]`}
      >
        <span>
          <strong className="font-semibold text-[#171a22]">Client tone &amp; style notes:</strong> Not set yet. Adding brand voice notes guides rewrites and recommendations.
        </span>
        <Link
          href={`/${clientSlug}/settings`}
          className="flex-none font-semibold text-[#00857b] hover:underline"
        >
          Add in Settings →
        </Link>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border border-[#ececec] bg-white ${
        compact ? "px-3.5 py-2.5" : "px-4 py-3"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          Client tone &amp; style notes
        </span>
        <Link
          href={`/${clientSlug}/settings`}
          className="text-xs font-semibold text-[#00857b] hover:underline"
        >
          Edit in Settings →
        </Link>
      </div>
      <p className="mt-1 whitespace-pre-line text-[13px] text-[#171a22]">{clean}</p>
    </div>
  );
}

export function PriorRejectionsCard({ rejections }: { rejections: PriorRejection[] }) {
  if (rejections.length === 0) return null;
  return (
    <div
      className="rounded-xl border bg-white px-4 py-3"
      style={{ borderColor: TONE.warn.border }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-[0.12em]" style={{ color: TONE.warn.fg }}>
          Prior reviewer rejections on this page ({rejections.length})
        </span>
      </div>
      <ul className="mt-2 space-y-2">
        {rejections.map((r) => (
          <li
            key={r.id}
            className="rounded-[10px] border border-[#f1f2f3] bg-[#f8f8f8] px-3 py-2 text-xs text-[#171a22]"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill t="miss">{r.rejection_reason_label ?? r.rejection_reason ?? "Rejected"}</Pill>
              <span className="font-semibold text-[#0a0c0f]">“{r.search}”</span>
              <span className="text-[#7a838c]">· {r.month}</span>
              {r.rejected_at ? <span className="text-[#7a838c]">· {formatDay(r.rejected_at, true)}</span> : null}
              {r.rejected_by ? <span className="text-[#7a838c]">by {r.rejected_by.split("@")[0]}</span> : null}
            </div>
            {r.rejection_note ? <p className="mt-1 text-[#4a5560]">{r.rejection_note}</p> : null}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function RejectForm({
  reasons = REJECTION_REASONS,
  busy = false,
  allowDropWithoutReason = false,
  onSubmit,
  onCancel,
}: {
  reasons?: RejectionReason[];
  busy?: boolean;
  allowDropWithoutReason?: boolean;
  onSubmit: (payload: { status: "rejected" | "dropped"; rejection_reason?: string; rejection_note?: string }) => void;
  onCancel: () => void;
}) {
  const list = reasons.length > 0 ? reasons : REJECTION_REASONS;
  const [reason, setReason] = useState<string>(list[0]?.key ?? "");
  const [note, setNote] = useState("");

  return (
    <div className="rounded-xl border border-[#ececec] bg-white p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          Reviewer feedback — choose a rejection reason
        </span>
        <button
          type="button"
          onClick={onCancel}
          className="cursor-pointer text-xs font-semibold text-[#7a838c] hover:text-[#0a0c0f]"
        >
          Cancel
        </button>
      </div>

      <div className="mt-2.5 flex flex-wrap gap-1.5" role="radiogroup" aria-label="Rejection reason">
        {list.map((r) => {
          const active = reason === r.key;
          return (
            <button
              key={r.key}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => setReason(r.key)}
              className="cursor-pointer rounded-full border px-3 py-1 text-xs font-semibold transition-colors"
              style={
                active
                  ? { background: DARK, borderColor: DARK, color: "#fff" }
                  : { background: "#fff", borderColor: "#e3e6e8", color: "#4a5560" }
              }
            >
              {r.label}
            </button>
          );
        })}
      </div>

      <div className="mt-3">
        <label className="block text-xs font-semibold text-[#4a5560]">
          Optional note for the team
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            placeholder="Why this recommendation should be skipped or changed…"
            className="mt-1 w-full rounded-[10px] border border-[#e3e6e8] bg-white px-3 py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:border-[#00a99d] focus:outline-none"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={busy || !reason}
          onClick={() =>
            onSubmit({
              status: "rejected",
              rejection_reason: reason,
              rejection_note: note.trim() || undefined,
            })
          }
          className="cursor-pointer rounded-full px-4 py-1.5 text-xs font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50"
          style={{ background: "oklch(0.48 0.17 25)" }}
        >
          {busy ? "Saving…" : "Reject with reason"}
        </button>
        {allowDropWithoutReason ? (
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              onSubmit({
                status: "dropped",
                ...(reason ? { rejection_reason: reason } : {}),
                ...(note.trim() ? { rejection_note: note.trim() } : {}),
              })
            }
            className="cursor-pointer rounded-full border border-[#e3e6e8] bg-white px-4 py-1.5 text-xs font-semibold text-[#4a5560] hover:bg-[#f6f7f7] disabled:opacity-50"
          >
            Drop from plan
          </button>
        ) : null}
      </div>
    </div>
  );
}
