"use client";

import type { ActionContext, EngineKind } from "@/lib/engine";

const FIT_BADGE: Record<string, { label: string; cls: string }> = {
  high: { label: "Suits the search", cls: "bg-[#e9fedc] text-[#2f5a00]" },
  medium: { label: "Partial fit", cls: "bg-[oklch(0.97_0.045_85)] text-[oklch(0.42_0.1_65)]" },
  low: { label: "Does not suit search", cls: "bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]" },
  unverified: { label: "Fit unverified", cls: "bg-[#f1f3f4] text-[#4a5560]" },
};

const FOCUS_LABELS: Record<EngineKind, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  leads: "Leads",
};

export function ContextHeader({
  intent,
  pageType,
  fit,
  template,
  focus,
  focusOrderReason,
}: {
  intent?: ActionContext["intent"];
  pageType?: ActionContext["page_type"];
  fit?: ActionContext["fit"];
  template?: ActionContext["template"];
  focus?: EngineKind;
  focusOrderReason?: string | null;
}) {
  if (!intent && !pageType && !fit && !template && !focus && !focusOrderReason) return null;

  const fitMeta = fit ? (FIT_BADGE[fit.level] ?? FIT_BADGE.unverified) : null;

  return (
    <div className="rounded-xl border border-[#ececec] bg-[#f8f8f8] p-3.5 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        {focus ? (
          <span className="rounded-full bg-[#223540] px-2.5 py-0.5 text-[11px] font-semibold text-white">
            Focus: {FOCUS_LABELS[focus]}
          </span>
        ) : null}

        {intent ? (
          <span
            className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
              intent.read
                ? "bg-[#e6f7f5] text-[#00665f]"
                : "bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]"
            }`}
          >
            Intent: {intent.read ? intent.name : "Not read"}
            {intent.read && intent.confidence ? ` (${intent.confidence})` : ""}
          </span>
        ) : null}

        {pageType ? (
          <span className="rounded-full bg-white border border-[#e3e6e8] px-2.5 py-0.5 text-[11px] font-semibold text-[#171a22]">
            Page type: {pageType.name}
          </span>
        ) : null}

        {fitMeta ? (
          <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${fitMeta.cls}`}>
            {fitMeta.label}
          </span>
        ) : null}

        {template ? (
          <span className="rounded-full bg-[#f1f3f4] px-2.5 py-0.5 text-[11px] font-semibold text-[#4a5560]">
            {template.shared === true
              ? `Shared template (${template.peers} peers)`
              : template.shared === false
                ? "Unique page layout"
                : "Template unverified"}
          </span>
        ) : null}
      </div>

      <div className="mt-2 space-y-1 text-[12px] text-[#4a5560]">
        {fit?.why ? (
          <p>
            <strong className="text-[#171a22]">Fit:</strong> {fit.why}
          </p>
        ) : null}
        {intent?.searcher_goal ? (
          <p>
            <strong className="text-[#171a22]">Searcher goal:</strong> {intent.searcher_goal}
          </p>
        ) : intent && !intent.read && intent.uncertainty ? (
          <p>
            <strong className="text-[#171a22]">Intent note:</strong> {intent.uncertainty}
          </p>
        ) : null}
        {template?.note ? (
          <p>
            <strong className="text-[#171a22]">Template:</strong> {template.note}
          </p>
        ) : null}
        {focusOrderReason ? (
          <p>
            <strong className="text-[#171a22]">Priority order:</strong> {focusOrderReason}
          </p>
        ) : null}
      </div>
    </div>
  );
}
