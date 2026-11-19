"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { triggerSiteCrawlAction } from "@/app/(app)/[clientSlug]/site-health/actions";
import type { Client } from "@/lib/api";
import { monthLabel } from "@/lib/focus";
import type { ShData, ShPageEntry, ShPageIssue, ShResponse } from "@/lib/site-health";
import {
  buildUnifiedFixes,
  chipLabelForIssue,
  filterPages,
  fixIdForPageIssue,
  fixIdForSignal,
  type FixGroup,
  type FixOwner,
  type UnifiedFix,
} from "@/lib/site-health-fixes";

type FixStatus = "sent" | "done";

const shortPath = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const shortDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric" });
const fullDay = (iso: string) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

const ringColor = (score: number) => (score >= 70 ? "#00a99d" : "oklch(0.62 0.2 25)");
const overviewColor = (score: number) =>
  score >= 80 ? "#00a99d" : score >= 50 ? "oklch(0.68 0.16 65)" : "oklch(0.62 0.2 25)";

function downloadCsv(filename: string, rows: string[][]) {
  const escape = (cell: string) => `"${cell.replace(/"/g, '""')}"`;
  const csv = rows.map((r) => r.map(escape).join(",")).join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function ScoreCard({
  label,
  question,
  score,
  grade,
  gainAvailable,
}: {
  label: string;
  question: string;
  score: number;
  grade: string;
  gainAvailable: number;
}) {
  const r = 23;
  const circ = 2 * Math.PI * r;
  const color = ringColor(score);
  const dash = `${((Math.max(0, Math.min(100, score)) / 100) * circ).toFixed(1)} ${circ.toFixed(1)}`;

  return (
    <div className="flex min-w-[240px] flex-none items-center gap-3.5 rounded-xl border border-[#ececec] bg-white px-4 py-2.5 pl-3">
      <div className="relative h-14 w-14 flex-none">
        <svg width="56" height="56" viewBox="0 0 56 56" role="img" aria-label={`${label}: ${score} out of 100, grade ${grade}`}>
          <circle cx="28" cy="28" r={r} fill="none" stroke="#eef0f1" strokeWidth="6" />
          <circle
            cx="28"
            cy="28"
            r={r}
            fill="none"
            stroke={color}
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={dash}
            transform="rotate(-90 28 28)"
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center font-[var(--font-heading)] text-[18px] font-bold text-[#0a0c0f] tabular-nums">
          {score}
        </div>
      </div>
      <div className="min-w-0">
        <div className="flex items-baseline gap-1.5">
          <span className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">{label}</span>
          <span className="text-xs font-bold" style={{ color }}>
            {grade}
          </span>
        </div>
        <div className="text-xs text-[#4a5560]">{question}</div>
        <div className="text-xs font-semibold text-[#00857b] tabular-nums">
          {gainAvailable > 0 ? `+${gainAvailable} available below` : "All checks passing"}
        </div>
      </div>
    </div>
  );
}

function GainPills({
  seoGain,
  geoGain,
  owner,
  size = "sm",
}: {
  seoGain?: number;
  geoGain?: number;
  owner?: FixOwner;
  size?: "sm" | "md";
}) {
  const pad = size === "md" ? "px-2.5 py-0.5 text-[11px]" : "px-2 py-0 text-[10px]";
  return (
    <div className="flex flex-wrap items-center gap-1">
      {seoGain != null && seoGain > 0 ? (
        <span className={`rounded-full bg-[#e6f7f5] font-bold text-[#00665f] tabular-nums ${pad}`}>
          SEO +{seoGain}
        </span>
      ) : null}
      {geoGain != null && geoGain > 0 ? (
        <span className={`rounded-full bg-[#e9fedc] font-bold text-[#2f5a00] tabular-nums ${pad}`}>
          GEO +{geoGain}
        </span>
      ) : null}
      {owner ? (
        <span className={`rounded-full bg-[#f1f3f4] font-semibold text-[#4a5560] ${pad}`}>
          {size === "md" ? `Owner: ${owner}` : owner}
        </span>
      ) : null}
    </div>
  );
}

function StatusBadge({ status, awaitingCrawl }: { status: FixStatus; awaitingCrawl: boolean }) {
  if (status === "sent") {
    return (
      <span className="rounded-full bg-[#eef0f1] px-2 py-0 text-[10px] font-semibold text-[#4a5560]">
        Sent to Teamwork
      </span>
    );
  }
  return (
    <span className="rounded-full bg-[#c6f2ed] px-2 py-0 text-[10px] font-semibold text-[#00665f]">
      {awaitingCrawl ? "Marked fixed · awaiting crawl" : "Fixed ✓"}
    </span>
  );
}

function AffectedGroupCard({ group, fixId }: { group: FixGroup; fixId: string }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? group.items : group.items.slice(0, 6);
  const remaining = Math.max(0, group.totalCount - shown.length);

  return (
    <div className="overflow-hidden rounded-xl border border-[#ececec] bg-white">
      <div className="flex items-center justify-between gap-3 border-b border-[#f1f2f3] px-[18px] py-3">
        <div className="min-w-0">
          <div className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">{group.title}</div>
          <div className="text-xs text-[#7a838c]">{group.sub}</div>
        </div>
        {group.link ? (
          <Link
            href={group.link.href}
            className="flex-none text-xs font-semibold text-[#00a99d] hover:text-[#00756d]"
          >
            {group.link.label} →
          </Link>
        ) : null}
      </div>

      <div>
        {shown.map((item, idx) => (
          <div
            key={`${item.a}-${idx}`}
            className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-[#f6f7f7] px-[18px] py-2.5 text-[13px] last:border-b-0"
          >
            <div className="min-w-0">
              <div className="truncate text-[#171a22]">
                {item.href ? (
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[#171a22] hover:text-[#00857b] hover:underline"
                  >
                    {item.a}
                  </a>
                ) : (
                  item.a
                )}
              </div>
              {item.b ? <div className="truncate text-xs text-[#7a838c]">{item.b}</div> : null}
            </div>
            <span className="flex-none text-xs text-[#7a838c] tabular-nums">{item.c}</span>
          </div>
        ))}
      </div>

      {remaining > 0 || group.csvRows.length > 1 ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-[#f1f2f3] px-[18px] py-2.5 text-xs text-[#7a838c]">
          {remaining > 0 ? <span>+ {remaining} more</span> : null}
          {remaining > 0 && group.items.length > 6 ? (
            <>
              <span>·</span>
              <button
                type="button"
                onClick={() => setExpanded((v) => !v)}
                className="cursor-pointer font-semibold text-[#223540] hover:underline"
              >
                {expanded ? "Show fewer" : "Show all loaded"}
              </button>
            </>
          ) : null}
          {group.csvRows.length > 1 ? (
            <>
              {remaining > 0 ? <span>·</span> : null}
              <button
                type="button"
                onClick={() => downloadCsv(`${fixId.replace(/[:/]/g, "-")}.csv`, group.csvRows)}
                className="cursor-pointer font-semibold text-[#00a99d] hover:text-[#00756d]"
              >
                Download CSV
              </button>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function FixDetailPane({
  fix,
  status,
  copied,
  onAdvanceStatus,
  onCopySteps,
}: {
  fix: UnifiedFix;
  status: FixStatus | undefined;
  copied: boolean;
  onAdvanceStatus: () => void;
  onCopySteps: () => void;
}) {
  const isDone = status === "done";
  const isSent = status === "sent";
  const btnLabel = isDone
    ? fix.affected > 0
      ? "Marked fixed · awaiting crawl"
      : "Fixed ✓"
    : isSent
      ? "Mark as fixed"
      : "Send to Teamwork";
  const btnClass = isDone
    ? "bg-[#c6f2ed] text-[#00665f] cursor-default"
    : isSent
      ? "bg-[#00a99d] text-white hover:bg-[#008077]"
      : "bg-[#223540] text-white hover:opacity-90";

  return (
    <div className="min-w-0 flex-1 overflow-y-auto bg-[#f6f7f7]">
      <div className="border-b border-[#e8e8e8] bg-white px-7 py-4.5">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0 flex-1">
            <GainPills seoGain={fix.seo?.gain} geoGain={fix.geo?.gain} owner={fix.owner} size="md" />
            <h2 className="mt-1.5 font-[var(--font-heading)] text-[22px] font-bold text-[#0a0c0f]">
              {fix.name}
            </h2>
            <p className="mt-0.5 max-w-[640px] text-sm text-[#4a5560]">{fix.problem}</p>
          </div>
          <div className="flex flex-none flex-col items-end gap-2">
            <button
              type="button"
              disabled={isDone}
              onClick={onAdvanceStatus}
              className={`cursor-pointer rounded-full px-4 py-2 text-[13px] font-semibold transition-opacity ${btnClass}`}
            >
              {btnLabel}
            </button>
            <div className="flex items-center gap-3">
              {fix.toolLink ? (
                <Link
                  href={fix.toolLink.href}
                  className="text-xs font-semibold text-[#223540] underline underline-offset-2 hover:text-[#00857b]"
                >
                  {fix.toolLink.label} →
                </Link>
              ) : null}
              <button
                type="button"
                onClick={onCopySteps}
                className="cursor-pointer text-xs font-semibold text-[#00857b] hover:text-[#00665f]"
              >
                {copied ? "Copied ✓" : "Copy fix steps"}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-3.5 px-7 py-4.5 pb-8">
        <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            How to fix
          </div>
          <div className="mt-2.5 space-y-2">
            {fix.steps.map((step, idx) => (
              <div key={idx} className="flex items-start gap-2.5 text-sm text-[#171a22]">
                <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
                  {idx + 1}
                </span>
                <span>{step}</span>
              </div>
            ))}
          </div>
          {fix.note ? <div className="mt-2.5 text-xs text-[#7a838c]">{fix.note}</div> : null}
        </div>

        {fix.groups.map((group, idx) => (
          <AffectedGroupCard key={`${fix.id}-${group.title}-${idx}`} group={group} fixId={fix.id} />
        ))}
      </div>
    </div>
  );
}

function PageDetailPane({
  page,
  scope,
  clientSlug,
  sent,
  onSendPage,
  onOpenFix,
}: {
  page: ShPageEntry;
  scope: "all" | "seo" | "geo";
  clientSlug: string;
  sent: boolean;
  onSendPage: () => void;
  onOpenFix: (fixId: string) => void;
}) {
  const items = scope === "all" ? page.issues : page.issues.filter((i) => i.source === scope);

  return (
    <div className="min-w-0 flex-1 overflow-y-auto bg-[#f6f7f7]">
      <div className="border-b border-[#e8e8e8] bg-white px-7 py-4.5">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0 flex-1">
            <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">Page</div>
            <div className="mt-0.5 flex flex-wrap items-baseline gap-2.5">
              <h2 className="break-all font-[var(--font-heading)] text-[20px] font-bold text-[#0a0c0f]">
                {shortPath(page.url)}
              </h2>
              <a
                href={page.url}
                target="_blank"
                rel="noreferrer"
                className="text-xs font-semibold text-[#00a99d] hover:text-[#00756d]"
              >
                Open URL ↗
              </a>
            </div>
            <p className="mt-0.5 text-[13px] text-[#4a5560]">
              {items.length} {items.length === 1 ? "thing" : "things"} to fix on this page. The same fixes as the By fix view, filtered to this one address.
            </p>
          </div>
          <button
            type="button"
            onClick={onSendPage}
            className={`flex-none cursor-pointer rounded-full px-4 py-2 text-[13px] font-semibold text-white transition-opacity ${
              sent ? "bg-[#00a99d]" : "bg-[#223540] hover:opacity-90"
            }`}
          >
            {sent ? "Sent to Teamwork ✓" : "Send page fixes to Teamwork"}
          </button>
        </div>
      </div>

      <div className="space-y-2.5 px-7 py-4.5 pb-8">
        {items.map((issue: ShPageIssue, idx) => {
          const isSeo = issue.source === "seo";
          const fixId = fixIdForPageIssue(issue);
          const toolHref =
            issue.key === "schema"
              ? `/${clientSlug}/schema`
              : issue.key === "titles" || issue.key === "dup_titles" || issue.key === "descriptions" || issue.key === "dup_descriptions"
                ? `/${clientSlug}/ctr`
                : null;
          const toolLabel =
            issue.key === "schema"
              ? "Open Machine Readability"
              : toolHref
                ? "Open CTR Optimizer"
                : null;

          return (
            <div
              key={`${issue.source}-${issue.key}-${issue.subject ?? ""}-${idx}`}
              className="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-[#ececec] bg-white px-[18px] py-3.5"
            >
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-bold text-[#0a0c0f]">{issue.label}</span>
                  <span
                    className={`rounded-full px-2 py-0 text-[10px] font-bold ${
                      isSeo ? "bg-[#e6f7f5] text-[#00665f]" : "bg-[#e9fedc] text-[#2f5a00]"
                    }`}
                  >
                    {issue.source.toUpperCase()}
                  </span>
                </div>
                <div className="text-[13px] text-[#4a5560]">{issue.problem}</div>
                <div className="text-[13px] text-[#171a22]">
                  <strong>Fix:</strong> {issue.fix}
                </div>
                {toolHref && toolLabel ? (
                  <div className="pt-0.5">
                    <Link href={toolHref} className="text-xs font-semibold text-[#00857b] hover:underline">
                      {toolLabel} →
                    </Link>
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                onClick={() => onOpenFix(fixId)}
                className="flex-none cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3 py-1 text-xs font-semibold text-[#223540] transition-colors hover:border-[#e6f7f5] hover:bg-[#e6f7f5]"
              >
                See all pages
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

type SignalRow = {
  id: string;
  label: string;
  score: number | null;
  weight: number;
  measured: boolean;
  fixId?: string;
};

function OverviewScoreCard({
  title,
  question,
  score,
  grade,
  previousScore,
  previousDate,
  projectedScore,
  openFixCount,
  signals,
  onSelectFix,
}: {
  title: string;
  question: string;
  score: number;
  grade: string;
  previousScore: number | null | undefined;
  previousDate?: string | null;
  projectedScore: number;
  openFixCount: number;
  signals: SignalRow[];
  onSelectFix: (fixId: string) => void;
}) {
  const r = 41;
  const circ = 2 * Math.PI * r;
  const color = overviewColor(score);
  const dash = `${((Math.max(0, Math.min(100, score)) / 100) * circ).toFixed(1)} ${circ.toFixed(1)}`;
  const delta = previousScore != null ? score - previousScore : null;

  return (
    <div className="rounded-xl border border-[#ececec] bg-white px-[22px] py-5">
      <div className="flex flex-wrap items-center gap-5">
        <div className="relative h-24 w-24 flex-none">
          <svg width="96" height="96" viewBox="0 0 96 96" role="img" aria-label={`${title}: ${score} out of 100, grade ${grade}`}>
            <circle cx="48" cy="48" r={r} fill="none" stroke="#eef0f1" strokeWidth="9" />
            <circle
              cx="48"
              cy="48"
              r={r}
              fill="none"
              stroke={color}
              strokeWidth="9"
              strokeLinecap="round"
              strokeDasharray={dash}
              transform="rotate(-90 48 48)"
            />
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center leading-none">
            <span className="font-[var(--font-heading)] text-[30px] font-bold text-[#0a0c0f] tabular-nums">{score}</span>
            <span className="mt-0.5 text-xs font-bold" style={{ color }}>
              {grade}
            </span>
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <h2 className="font-[var(--font-heading)] text-[20px] font-bold text-[#0a0c0f]">{title}</h2>
          <p className="text-[13px] text-[#4a5560]">{question}</p>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <div>
              <div className="text-[11px] font-semibold text-[#7a838c]">After top 3</div>
              <div className="font-[var(--font-heading)] text-[15px] font-bold text-[#00857b] tabular-nums">
                {score} → {projectedScore}
              </div>
            </div>
            <div>
              <div className="text-[11px] font-semibold text-[#7a838c]">Fixes open</div>
              <div className="font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f] tabular-nums">
                {openFixCount}
              </div>
            </div>
            <div>
              <div className="text-[11px] font-semibold text-[#7a838c]">
                {previousDate ? `Vs. ${shortDay(previousDate)}` : "Vs. earlier crawl"}
              </div>
              {delta == null ? (
                <div className="text-xs font-semibold text-[#7a838c]">— no prior crawl</div>
              ) : delta === 0 ? (
                <div className="text-xs font-semibold text-[#4a5560]">No change</div>
              ) : (
                <div className={`font-[var(--font-heading)] text-[15px] font-bold tabular-nums ${delta > 0 ? "text-[#00857b]" : "text-red-700"}`}>
                  {delta > 0 ? "▲" : "▼"} {Math.abs(delta)}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="mt-4 border-t border-[#eef0f1] pt-3">
        <div className="mb-1.5 grid grid-cols-[minmax(0,1fr)_140px_42px_48px] items-center gap-2 text-[10px] font-bold uppercase tracking-[0.1em] text-[#7a838c]">
          <span>Signal</span>
          <span>Score</span>
          <span className="text-right">Pts</span>
          <span className="text-right">Wt</span>
        </div>
        <div className="divide-y divide-[#f6f7f7]">
          {signals.map((sig) => {
            const c = sig.measured && sig.score != null ? overviewColor(sig.score) : "#d3d7d9";
            const w = sig.measured && sig.score != null ? Math.max(0, Math.min(100, sig.score)) : 0;
            const clickable = Boolean(sig.fixId);
            const rowContent = (
              <>
                <span className={`truncate text-xs ${clickable ? "font-semibold text-[#0a0c0f] group-hover:text-[#00857b]" : "text-[#4a5560]"}`}>
                  {sig.label}
                </span>
                <span className="h-1.5 w-[140px] overflow-hidden rounded-full bg-[#eef0f1]">
                  <span className="block h-full rounded-full" style={{ width: `${w}%`, background: c }} />
                </span>
                <span className="text-right text-xs font-bold tabular-nums" style={{ color: sig.measured ? c : "#7a838c" }}>
                  {sig.measured && sig.score != null ? sig.score : "—"}
                </span>
                <span className="text-right text-xs text-[#7a838c] tabular-nums">{sig.weight}</span>
              </>
            );

            return clickable && sig.fixId ? (
              <button
                key={sig.id}
                type="button"
                onClick={() => onSelectFix(sig.fixId!)}
                className="group grid w-full cursor-pointer grid-cols-[minmax(0,1fr)_140px_42px_48px] items-center gap-2 py-1.5 text-left hover:bg-[#f8f8f8]"
              >
                {rowContent}
              </button>
            ) : (
              <div key={sig.id} className="grid grid-cols-[minmax(0,1fr)_140px_42px_48px] items-center gap-2 py-1.5">
                {rowContent}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function HeadlineCard({
  eyebrow,
  value,
  ofTotal,
  pct,
  barColor,
  note,
}: {
  eyebrow: string;
  value: string;
  ofTotal?: string;
  pct: number;
  barColor: string;
  note: string;
}) {
  return (
    <div className="rounded-xl border border-[#ececec] bg-white px-4 py-3.5">
      <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">{eyebrow}</div>
      <div className="mt-1 flex items-baseline gap-1.5">
        <span className="font-[var(--font-heading)] text-[28px] font-bold leading-tight text-[#0a0c0f] tabular-nums">
          {value}
        </span>
        {ofTotal ? <span className="text-xs text-[#4a5560]">{ofTotal}</span> : null}
      </div>
      <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-[#eef0f1]">
        <div className="h-full rounded-full" style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: barColor }} />
      </div>
      <div className="mt-1.5 truncate text-xs text-[#4a5560]">{note}</div>
    </div>
  );
}

function OverviewTab({
  data,
  toFix,
  issueStatus,
  onSelectFix,
  onOpenFixes,
}: {
  data: ShData;
  toFix: UnifiedFix[];
  issueStatus: Record<string, FixStatus>;
  onSelectFix: (fixId: string) => void;
  onOpenFixes: () => void;
}) {
  const openIds = new Set(toFix.map((f) => f.id));

  const seoSignals: SignalRow[] = [...data.seo.checks]
    .sort((a, b) => b.weight - a.weight)
    .map((c) => {
      const fid = fixIdForSignal("seo", c.key);
      return {
        id: `seo-${c.key}`,
        label: c.label,
        score: c.score,
        weight: c.weight,
        measured: true,
        fixId: openIds.has(fid) ? fid : undefined,
      };
    });

  const geoSignals: SignalRow[] = [...data.geo.signals]
    .sort((a, b) => b.weight - a.weight)
    .map((s) => {
      const fid = fixIdForSignal("geo", s.key);
      return {
        id: `geo-${s.key}`,
        label: s.label,
        score: s.score,
        weight: s.weight,
        measured: s.measured,
        fixId: openIds.has(fid) ? fid : undefined,
      };
    });

  const top3 = toFix.slice(0, 3);
  const seoTop3Gain = top3.reduce((acc, f) => acc + (f.seo?.gain ?? 0), 0);
  const geoTop3Gain = top3.reduce((acc, f) => acc + (f.geo?.gain ?? 0), 0);
  const seoProjected = Math.min(100, Math.round(data.seo.score + seoTop3Gain));
  const geoProjected = Math.min(100, Math.round(data.geo.score + geoTop3Gain));

  const seoFixCount = toFix.filter((f) => (f.seo?.gain ?? 0) > 0).length;
  const geoFixCount = toFix.filter((f) => (f.geo?.gain ?? 0) > 0).length;

  const totalCrawled = data.crawl.pages;
  const healthyPages = Math.max(0, totalCrawled - (data.by_page?.length ?? 0));
  const healthyPct = totalCrawled > 0 ? Math.round((healthyPages / totalCrawled) * 100) : 0;

  const citationSig = data.geo.signals.find((s) => s.key === "citation");
  const citationDetail = (citationSig?.detail ?? {}) as { cited?: number; answers?: number };
  const answersTotal = citationDetail.answers ?? data.geo.answers?.answers ?? 0;
  const answersCited = citationDetail.cited ?? 0;
  const citedPct = answersTotal > 0 ? Math.round((answersCited / answersTotal) * 100) : 0;

  const platformsNaming = data.geo.answers?.platforms_naming ?? [];
  const platformsTotal = 4;
  const brandPct = Math.round((platformsNaming.length / platformsTotal) * 100);

  const doneCount = toFix.filter((f) => issueStatus[f.id] === "done").length;
  const sentCount = toFix.filter((f) => issueStatus[f.id] === "sent").length;
  const progressPct = toFix.length > 0 ? Math.round(((doneCount + sentCount * 0.5) / toFix.length) * 100) : 100;

  const owners: FixOwner[] = ["Developer", "Content", "SEO"];
  const ownerStats = owners.map((owner) => {
    const list = toFix.filter((f) => f.owner === owner);
    const seoPts = +list.reduce((a, f) => a + (f.seo?.gain ?? 0), 0).toFixed(1);
    const geoPts = +list.reduce((a, f) => a + (f.geo?.gain ?? 0), 0).toFixed(1);
    return {
      owner,
      count: list.length,
      seoPts,
      geoPts,
      total: +(seoPts + geoPts).toFixed(1),
    };
  });
  const maxOwnerPts = Math.max(1, ...ownerStats.map((o) => o.total));

  return (
    <div className="flex-1 overflow-y-auto px-6 py-5">
      <div className="space-y-4">
        {/* Row 1: Two large score cards with signal breakdown */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <OverviewScoreCard
            title="SEO health"
            question="Is the site sound for search?"
            score={data.seo.score}
            grade={data.seo.grade}
            previousScore={data.previous?.seo}
            previousDate={data.previous?.crawl_date}
            projectedScore={seoProjected}
            openFixCount={seoFixCount}
            signals={seoSignals}
            onSelectFix={onSelectFix}
          />
          <OverviewScoreCard
            title="GEO readiness"
            question="Can AI answers read and cite it?"
            score={data.geo.score}
            grade={data.geo.grade}
            previousScore={data.previous?.geo}
            previousDate={data.previous?.crawl_date}
            projectedScore={geoProjected}
            openFixCount={geoFixCount}
            signals={geoSignals}
            onSelectFix={onSelectFix}
          />
        </div>

        {/* Row 2: Four headline cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <HeadlineCard
            eyebrow="Healthy pages"
            value={healthyPages.toLocaleString("en-US")}
            ofTotal={`of ${totalCrawled.toLocaleString("en-US")} crawled`}
            pct={healthyPct}
            barColor={overviewColor(healthyPct)}
            note={`${healthyPct}% have zero open SEO or GEO issues`}
          />
          <HeadlineCard
            eyebrow="AI answers citing you"
            value={answersTotal > 0 ? String(answersCited) : "—"}
            ofTotal={answersTotal > 0 ? `of ${answersTotal} answers` : "No LLM run yet"}
            pct={citedPct}
            barColor={answersTotal > 0 ? overviewColor(citedPct) : "#d3d7d9"}
            note={answersTotal > 0 ? `${citedPct}% citation rate across prompts` : "Run LLM visibility to measure"}
          />
          <HeadlineCard
            eyebrow="Brand known by AI"
            value={data.geo.answers ? String(platformsNaming.length) : "—"}
            ofTotal={data.geo.answers ? `of ${platformsTotal} platforms` : "No LLM run yet"}
            pct={brandPct}
            barColor={data.geo.answers ? overviewColor(brandPct) : "#d3d7d9"}
            note={
              platformsNaming.length > 0
                ? platformsNaming.join(", ")
                : "ChatGPT, Claude, Gemini, Perplexity"
            }
          />
          <HeadlineCard
            eyebrow="Fix progress"
            value={`${doneCount} fixed`}
            ofTotal={`· ${sentCount} in Teamwork`}
            pct={progressPct}
            barColor="#00a99d"
            note={`${toFix.length} open fixes tracked for ${monthLabel(data.month)}`}
          />
        </div>

        {/* Row 3: Start with these 3 (1.6fr) + Points by owner (1fr) */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[1.6fr_1fr]">
          <div className="rounded-xl border border-[#ececec] bg-white p-5">
            <div className="flex items-baseline justify-between gap-3">
              <div>
                <h2 className="font-[var(--font-heading)] text-[17px] font-bold text-[#0a0c0f]">
                  Start with these 3
                </h2>
                <p className="text-xs text-[#4a5560]">Highest total points across SEO and GEO</p>
              </div>
              <button
                type="button"
                onClick={onOpenFixes}
                className="cursor-pointer text-xs font-semibold text-[#00857b] hover:text-[#00665f]"
              >
                See all {toFix.length} fixes →
              </button>
            </div>

            {top3.length === 0 ? (
              <p className="mt-4 text-sm text-[#4a5560]">All checks are passing in this crawl.</p>
            ) : (
              <div className="mt-3 divide-y divide-[#f1f2f3]">
                {top3.map((fix, idx) => (
                  <button
                    key={fix.id}
                    type="button"
                    onClick={() => onSelectFix(fix.id)}
                    className="flex w-full cursor-pointer items-center gap-3 py-3 text-left transition-colors hover:bg-[#f8f8f8]"
                  >
                    <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full bg-[#223540] text-xs font-bold text-white">
                      {idx + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-semibold text-[#0a0c0f]">{fix.name}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        <GainPills seoGain={fix.seo?.gain} geoGain={fix.geo?.gain} owner={fix.owner} />
                        <span className="text-xs text-[#7a838c]">
                          · {fix.affected.toLocaleString("en-US")} {fix.unit}
                        </span>
                      </div>
                    </div>
                    <div className="flex-none text-right">
                      <div className="font-[var(--font-heading)] text-[18px] font-bold text-[#0a0c0f] tabular-nums">
                        +{fix.totalGain}
                      </div>
                      <div className="text-[10px] text-[#7a838c]">points</div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="flex flex-col justify-between rounded-xl border border-[#ececec] bg-white p-5">
            <div>
              <h2 className="font-[var(--font-heading)] text-[17px] font-bold text-[#0a0c0f]">
                Points by owner
              </h2>
              <p className="text-xs text-[#4a5560]">Where the available score recovery sits</p>

              <div className="mt-4 space-y-4">
                {ownerStats.map((o) => {
                  const seoW = (o.seoPts / maxOwnerPts) * 100;
                  const geoW = (o.geoPts / maxOwnerPts) * 100;
                  return (
                    <div key={o.owner}>
                      <div className="flex items-baseline justify-between text-xs">
                        <span className="font-semibold text-[#0a0c0f]">{o.owner}</span>
                        <span className="text-[#4a5560] tabular-nums">
                          <strong className="text-[#0a0c0f]">+{o.total}</strong> · {o.count}{" "}
                          {o.count === 1 ? "fix" : "fixes"}
                        </span>
                      </div>
                      <div className="mt-1.5 flex h-2 w-full overflow-hidden rounded-full bg-[#eef0f1]">
                        {seoW > 0 ? <div className="h-full bg-[#00a99d]" style={{ width: `${seoW}%` }} /> : null}
                        {geoW > 0 ? <div className="h-full bg-[#aae437]" style={{ width: `${geoW}%` }} /> : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="mt-5 flex items-center gap-4 border-t border-[#eef0f1] pt-3 text-xs text-[#4a5560]">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-[#00a99d]" /> SEO points
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-[#aae437]" /> GEO points
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SplitView({ client, result, data }: { client: Client; result: ShResponse; data: ShData }) {
  const router = useRouter();
  const { toFix, passing, totalSeoGain, totalGeoGain } = useMemo(
    () => buildUnifiedFixes(data, client.slug),
    [data, client.slug],
  );
  const byPage = data.by_page ?? [];

  const [view, setView] = useState<"overview" | "work">("overview");
  const [mode, setMode] = useState<"issues" | "pages">("issues");
  const [scope, setScope] = useState<"all" | "seo" | "geo">("all");
  const [selectedFixId, setSelectedFixId] = useState<string>(toFix[0]?.id ?? "");
  const [selectedPageUrl, setSelectedPageUrl] = useState<string>(byPage[0]?.url ?? "");
  const [query, setQuery] = useState("");
  const [passingOpen, setPassingOpen] = useState(false);
  const [issueStatus, setIssueStatus] = useState<Record<string, FixStatus>>({});
  const [pageSent, setPageSent] = useState<Record<string, boolean>>({});
  const [copied, setCopied] = useState(false);
  const [crawlPending, startCrawl] = useTransition();
  const [crawlMsg, setCrawlMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const storageKey = `organiciq:site-health:${client.id}:${data.month}`;

  useEffect(() => {
    try {
      const raw = localStorage.getItem(storageKey);
      if (raw) {
        const parsed = JSON.parse(raw) as { issueStatus?: Record<string, FixStatus>; pageSent?: Record<string, boolean> };
        setIssueStatus(parsed.issueStatus ?? {});
        setPageSent(parsed.pageSent ?? {});
      } else {
        setIssueStatus({});
        setPageSent({});
      }
    } catch {
      setIssueStatus({});
      setPageSent({});
    }
  }, [storageKey]);

  useEffect(() => {
    return () => {
      if (copyTimer.current) clearTimeout(copyTimer.current);
    };
  }, []);

  const persistState = (nextIssueStatus: Record<string, FixStatus>, nextPageSent: Record<string, boolean>) => {
    try {
      localStorage.setItem(storageKey, JSON.stringify({ issueStatus: nextIssueStatus, pageSent: nextPageSent }));
    } catch {
      // Ignore storage quota errors
    }
  };

  const visibleFixes = useMemo(
    () =>
      toFix.filter((f) => {
        if (scope === "all") return true;
        if (scope === "seo") return Boolean(f.seo && f.seo.gain > 0);
        return Boolean(f.geo && f.geo.gain > 0);
      }),
    [toFix, scope],
  );

  const visiblePassing = useMemo(
    () =>
      passing.filter((p) => {
        if (scope === "all") return true;
        return p.tags.includes(scope === "seo" ? "SEO" : "GEO");
      }),
    [passing, scope],
  );

  const visiblePages = useMemo(() => filterPages(byPage, scope, query), [byPage, scope, query]);
  const shownPages = visiblePages.slice(0, 60);

  const activeFix = visibleFixes.find((f) => f.id === selectedFixId) ?? visibleFixes[0] ?? null;
  const activePage = visiblePages.find((p) => p.url === selectedPageUrl) ?? visiblePages[0] ?? null;

  const advanceFixStatus = (fixId: string) => {
    const cur = issueStatus[fixId];
    const nextVal: FixStatus = cur === "sent" ? "done" : "sent";
    const next = { ...issueStatus, [fixId]: nextVal };
    setIssueStatus(next);
    persistState(next, pageSent);
  };

  const markPageSent = (url: string) => {
    const next = { ...pageSent, [url]: true };
    setPageSent(next);
    persistState(issueStatus, next);
  };

  const copySteps = (fix: UnifiedFix) => {
    const text = `${fix.name}\n${fix.steps.map((s, i) => `${i + 1}. ${s}`).join("\n")}`;
    try {
      navigator.clipboard?.writeText(text);
    } catch {
      // Ignore clipboard failures in restricted contexts
    }
    setCopied(true);
    if (copyTimer.current) clearTimeout(copyTimer.current);
    copyTimer.current = setTimeout(() => setCopied(false), 1500);
  };

  const handleRunCrawl = () => {
    setCrawlMsg(null);
    startCrawl(async () => {
      const res = await triggerSiteCrawlAction(client.id, client.slug);
      if (res.ok) {
        setCrawlMsg({
          ok: true,
          text: res.queued.length > 0 ? "Site crawl queued ✓" : "Crawl already queued or up to date",
        });
      } else {
        setCrawlMsg({ ok: false, text: res.error });
      }
    });
  };

  return (
    <section className="-m-8 flex min-h-[calc(100vh-3.5rem)] flex-col bg-[#f6f7f7] lg:h-[calc(100vh-3.5rem)] lg:overflow-hidden">
      {/* Header */}
      <header className="flex flex-none flex-wrap items-center justify-between gap-6 border-b border-[#e8e8e8] bg-white px-6 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="font-[var(--font-heading)] text-2xl font-bold text-[#0a0c0f]">Site health</h1>
            {(result.crawls?.length ?? 0) > 1 ? (
              <>
                <select
                  aria-label="Current crawl date"
                  value={result.month ?? data.month}
                  onChange={(e) => {
                    const qs = new URLSearchParams({ month: e.target.value });
                    if (result.compare_to && result.compare_to !== e.target.value) {
                      qs.set("compare_to", result.compare_to);
                    }
                    router.push(`/${client.slug}/site-health?${qs.toString()}`);
                  }}
                  className="rounded-lg border border-[#e3e6e8] bg-white px-2.5 py-1 text-xs font-semibold text-[#223540] tabular-nums"
                >
                  {(result.crawls ?? []).map((c) => (
                    <option key={c.month} value={c.month}>
                      Crawl: {fullDay(c.crawl_date)}
                    </option>
                  ))}
                </select>
                <select
                  aria-label="Compare to earlier crawl"
                  value={result.compare_to ?? data.previous?.month ?? ""}
                  onChange={(e) => {
                    const qs = new URLSearchParams({ month: result.month ?? data.month });
                    if (e.target.value) qs.set("compare_to", e.target.value);
                    router.push(`/${client.slug}/site-health?${qs.toString()}`);
                  }}
                  className="rounded-lg border border-[#e3e6e8] bg-[#f8f8f8] px-2.5 py-1 text-xs font-medium text-[#4a5560] tabular-nums"
                >
                  <option value="">Compare to: none</option>
                  {(result.crawls ?? [])
                    .filter((c) => c.month !== (result.month ?? data.month))
                    .map((c) => (
                      <option key={c.month} value={c.month}>
                        Compare to: {fullDay(c.crawl_date)}
                      </option>
                    ))}
                </select>
              </>
            ) : (
              <span className="rounded-lg border border-[#e3e6e8] bg-white px-2.5 py-1 text-xs font-semibold text-[#223540] tabular-nums">
                Last crawl: {fullDay(data.crawl_date)}
              </span>
            )}
            <div role="tablist" aria-label="Site health section" className="flex gap-0.5 rounded-full bg-[#f1f3f4] p-[3px]">
              {(
                [
                  { id: "overview", label: "Overview" },
                  { id: "work", label: "Fixes" },
                ] as const
              ).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={view === t.id}
                  onClick={() => setView(t.id)}
                  className={`cursor-pointer rounded-full px-3.5 py-1 text-xs font-semibold transition-colors ${
                    view === t.id ? "bg-[#223540] text-white" : "text-[#4a5560] hover:text-[#0a0c0f]"
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
            <button
              type="button"
              disabled={crawlPending}
              onClick={handleRunCrawl}
              className="cursor-pointer rounded-full border border-[#d3d7d9] bg-white px-3 py-1 text-xs font-semibold text-[#223540] transition-colors hover:border-[#00a99d] hover:text-[#00857b] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {crawlPending ? "Starting crawl…" : "Run crawl"}
            </button>
            {crawlMsg ? (
              <span className={`text-xs font-semibold ${crawlMsg.ok ? "text-[#00857b]" : "text-red-700"}`}>
                {crawlMsg.text}
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-[13px] text-[#4a5560]">
            One list of fixes for search and AI answers, ranked by how many points each one recovers.
          </p>
          <div className="mt-1.5 flex items-center gap-1.5 text-xs text-[oklch(0.42_0.1_65)]">
            <span className="h-1.5 w-1.5 flex-none rounded-full bg-[oklch(0.76_0.15_75)]" />
            <span>
              {data.crawl.hit_limit
                ? `The crawl of ${shortDay(data.crawl_date)} stopped at its ${data.crawl.limit}-page limit, so the scores cover ${data.crawl.pages} pages, not necessarily the whole site.`
                : `Scored from the ${shortDay(data.crawl_date)} crawl (${data.crawl.pages} pages)${data.locked ? " · month locked" : ""}.`}
            </span>
          </div>
        </div>

        {view === "work" ? (
          <div className="flex flex-wrap items-center gap-3">
            <ScoreCard
              label="SEO health"
              question="Is the site sound for search?"
              score={data.seo.score}
              grade={data.seo.grade}
              gainAvailable={totalSeoGain}
            />
            <ScoreCard
              label="GEO readiness"
              question="Can AI answers read and cite it?"
              score={data.geo.score}
              grade={data.geo.grade}
              gainAvailable={totalGeoGain}
            />
          </div>
        ) : null}
      </header>

      {view === "overview" ? (
        <OverviewTab
          data={data}
          toFix={toFix}
          issueStatus={issueStatus}
          onSelectFix={(fixId) => {
            setSelectedFixId(fixId);
            setMode("issues");
            setScope("all");
            setView("work");
          }}
          onOpenFixes={() => setView("work")}
        />
      ) : (
      /* Split View */
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        {/* Left List Panel */}
        <aside className="flex w-full flex-none flex-col border-b border-[#e8e8e8] bg-white lg:w-[410px] lg:border-b-0 lg:border-r xl:w-[430px]">
          <div className="flex flex-col gap-2.5 border-b border-[#eef0f1] px-4 py-3">
            <div className="flex items-center justify-between gap-2.5">
              <div role="tablist" aria-label="Site health view mode" className="flex gap-0.5 rounded-full bg-[#f1f3f4] p-[3px]">
                {(
                  [
                    { id: "issues", label: "By fix" },
                    { id: "pages", label: "By page" },
                  ] as const
                ).map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="tab"
                    aria-selected={mode === m.id}
                    onClick={() => setMode(m.id)}
                    className={`cursor-pointer rounded-full px-3.5 py-1 text-xs font-semibold transition-colors ${
                      mode === m.id ? "bg-[#223540] text-white" : "text-[#4a5560] hover:text-[#0a0c0f]"
                    }`}
                  >
                    {m.label}
                  </button>
                ))}
              </div>

              <div className="flex gap-1">
                {(
                  [
                    { id: "all", label: "All" },
                    { id: "seo", label: "SEO" },
                    { id: "geo", label: "GEO" },
                  ] as const
                ).map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    aria-pressed={scope === s.id}
                    onClick={() => setScope(s.id)}
                    className={`cursor-pointer rounded-full border px-2.5 py-1 text-[11px] font-semibold transition-colors ${
                      scope === s.id
                        ? "border-[#223540] bg-[#223540] text-white"
                        : "border-[#e3e6e8] bg-white text-[#171a22] hover:bg-[#f8f8f8]"
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
            </div>

            {mode === "pages" ? (
              <div className="flex items-center gap-2 rounded-[10px] border border-[#e3e6e8] px-3">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#7a838c" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
                  <circle cx="11" cy="11" r="7" />
                  <path d="m20 20-3.5-3.5" />
                </svg>
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Find a page by address"
                  aria-label="Find a page by address"
                  className="flex-1 bg-transparent py-2 text-[13px] text-[#171a22] placeholder:text-[#7a838c] focus:outline-none"
                />
              </div>
            ) : null}
          </div>

          <div className="flex-1 overflow-y-auto">
            {mode === "issues" ? (
              <>
                <div className="px-4 pt-2.5 pb-1 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
                  To fix · {visibleFixes.length}
                </div>
                {visibleFixes.length === 0 ? (
                  <div className="px-4 py-6 text-sm text-[#4a5560]">No open fixes in this scope.</div>
                ) : (
                  visibleFixes.map((fix) => {
                    const selected = activeFix?.id === fix.id;
                    const st = issueStatus[fix.id];
                    return (
                      <button
                        key={fix.id}
                        type="button"
                        onClick={() => setSelectedFixId(fix.id)}
                        style={selected ? { boxShadow: "inset 3px 0 0 #00a99d" } : undefined}
                        className={`flex w-full cursor-pointer items-center gap-3 border-b border-[#f1f2f3] px-4 py-[11px] text-left transition-colors ${
                          selected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"
                        }`}
                      >
                        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-[13px] font-semibold text-[#0a0c0f]">{fix.name}</span>
                            {st ? <StatusBadge status={st} awaitingCrawl={fix.affected > 0} /> : null}
                          </div>
                          <div className="flex flex-wrap items-center gap-2 text-xs text-[#4a5560]">
                            <span>
                              {fix.affected.toLocaleString("en-US")} {fix.unit} to fix
                            </span>
                            {data.previous && fix.change ? (
                              <>
                                {fix.change.newCount > 0 ? (
                                  <span className="font-semibold text-red-700">▲ {fix.change.newCount} new</span>
                                ) : null}
                                {fix.change.fixedCount > 0 ? (
                                  <span className="font-semibold text-[#00857b]">✓ {fix.change.fixedCount} fixed</span>
                                ) : null}
                              </>
                            ) : null}
                          </div>
                          <GainPills seoGain={fix.seo?.gain} geoGain={fix.geo?.gain} owner={fix.owner} />
                        </div>
                        <div className="flex-none text-right">
                          <div className="font-[var(--font-heading)] text-[16px] font-bold text-[#0a0c0f] tabular-nums">
                            +{fix.totalGain}
                          </div>
                          <div className="text-[10px] text-[#7a838c]">points</div>
                        </div>
                      </button>
                    );
                  })
                )}

                {visiblePassing.length > 0 ? (
                  <>
                    <button
                      type="button"
                      onClick={() => setPassingOpen((v) => !v)}
                      className="flex w-full cursor-pointer items-center justify-between border-b border-[#f1f2f3] bg-[#fbfbfb] px-4 py-2.5 text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]"
                    >
                      <span>Passing · {visiblePassing.length}</span>
                      <span className="tracking-normal">{passingOpen ? "−" : "+"}</span>
                    </button>
                    {passingOpen
                      ? visiblePassing.map((p) => (
                          <div
                            key={p.id}
                            className="flex items-center justify-between gap-2.5 border-b border-[#f1f2f3] px-4 py-2 text-xs"
                          >
                            <span className="text-[#4a5560]">{p.name}</span>
                            <span className="flex gap-1">
                              {p.tags.map((t) => (
                                <span
                                  key={t}
                                  className="rounded-full bg-[#e6f7f5] px-2 py-0 text-[10px] font-bold text-[#00665f]"
                                >
                                  {t} ✓
                                </span>
                              ))}
                            </span>
                          </div>
                        ))
                      : null}
                  </>
                ) : null}
              </>
            ) : (
              <>
                <div className="px-4 pt-2.5 pb-1 text-xs text-[#7a838c]">
                  {visiblePages.length.toLocaleString("en-US")} {visiblePages.length === 1 ? "page has" : "pages have"} something to fix
                  {visiblePages.length > shownPages.length ? ` · showing top ${shownPages.length}` : ""}
                </div>
                {shownPages.length === 0 ? (
                  <div className="px-4 py-6 text-sm text-[#4a5560]">No pages match this filter.</div>
                ) : (
                  shownPages.map((page) => {
                    const selected = activePage?.url === page.url;
                    const scopedIssues =
                      scope === "all" ? page.issues : page.issues.filter((i) => i.source === scope);
                    const chips = scopedIssues.slice(0, 3).map(chipLabelForIssue);
                    const extra = scopedIssues.length - chips.length;

                    return (
                      <button
                        key={page.url}
                        type="button"
                        onClick={() => setSelectedPageUrl(page.url)}
                        style={selected ? { boxShadow: "inset 3px 0 0 #00a99d" } : undefined}
                        className={`flex w-full cursor-pointer items-center gap-3 border-b border-[#f1f2f3] px-4 py-[11px] text-left transition-colors ${
                          selected ? "bg-[#eef8f7]" : "bg-white hover:bg-[#f8f8f8]"
                        }`}
                      >
                        <div className="flex min-w-0 flex-1 flex-col gap-1">
                          <div className="truncate text-[13px] font-semibold text-[#0a0c0f]">
                            {shortPath(page.url)}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {chips.map((c, idx) => (
                              <span
                                key={`${c}-${idx}`}
                                className="rounded-full bg-[#f1f3f4] px-2 py-0 text-[10px] font-semibold text-[#4a5560]"
                              >
                                {c}
                              </span>
                            ))}
                            {extra > 0 ? (
                              <span className="rounded-full bg-[#f1f3f4] px-2 py-0 text-[10px] font-semibold text-[#4a5560]">
                                +{extra}
                              </span>
                            ) : null}
                          </div>
                        </div>
                        <div className="flex-none text-right">
                          <div className="font-[var(--font-heading)] text-[16px] font-bold text-[#0a0c0f] tabular-nums">
                            {scopedIssues.length}
                          </div>
                          <div className="text-[10px] text-[#7a838c]">to fix</div>
                        </div>
                      </button>
                    );
                  })
                )}
              </>
            )}
          </div>
        </aside>

        {/* Right Detail Panel */}
        {mode === "issues" ? (
          activeFix ? (
            <FixDetailPane
              fix={activeFix}
              status={issueStatus[activeFix.id]}
              copied={copied}
              onAdvanceStatus={() => advanceFixStatus(activeFix.id)}
              onCopySteps={() => copySteps(activeFix)}
            />
          ) : (
            <div className="flex flex-1 items-center justify-center p-8 text-sm text-[#4a5560]">
              Select a fix on the left to see steps and affected pages.
            </div>
          )
        ) : activePage ? (
          <PageDetailPane
            page={activePage}
            scope={scope}
            clientSlug={client.slug}
            sent={Boolean(pageSent[activePage.url])}
            onSendPage={() => markPageSent(activePage.url)}
            onOpenFix={(fixId) => {
              setSelectedFixId(fixId);
              setMode("issues");
            }}
          />
        ) : (
          <div className="flex flex-1 items-center justify-center p-8 text-sm text-[#4a5560]">
            Select a page on the left to inspect its fixes.
          </div>
        )}
      </div>
      )}
    </section>
  );
}

export function SiteHealth({
  client,
  result,
  error,
}: {
  client: Client;
  result: ShResponse | null;
  error: string | null;
}) {
  const data = result?.data ?? null;

  if (error) {
    return (
      <section className="max-w-4xl space-y-4">
        <h1 className="font-[var(--font-heading)] text-2xl font-bold">Site health</h1>
        <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      </section>
    );
  }

  if (!result || !data) {
    return (
      <section className="max-w-4xl space-y-4">
        <h1 className="font-[var(--font-heading)] text-2xl font-bold">Site health</h1>
        <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          This site has not been crawled yet, so there is nothing to score. Pull data on the{" "}
          <Link href={`/${client.slug}/settings/connections`} className="underline">
            Connections
          </Link>{" "}
          page starts a crawl.
        </p>
      </section>
    );
  }

  return <SplitView client={client} result={result} data={data} />;
}
