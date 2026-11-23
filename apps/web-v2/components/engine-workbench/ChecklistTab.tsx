"use client";

import type { ChecklistItem, EngineKind } from "@/lib/engine";
import { Pill, type Tone } from "@/components/engine-workbench/tokens";

const STATUS_META: Record<ChecklistItem["status"], { label: string; tone: Tone }> = {
  needed: { label: "Needed", tone: "miss" },
  check: { label: "Check", tone: "warn" },
  done: { label: "Done", tone: "ok" },
};

const FOCUS_LABEL: Record<EngineKind, string> = {
  visibility: "Visibility",
  traffic: "Traffic",
  leads: "Leads",
};

export function ChecklistTab({
  items,
  pageTypeName,
  pageTypeKey,
  focus,
}: {
  items: ChecklistItem[];
  pageTypeName?: string;
  pageTypeKey?: string;
  focus?: EngineKind;
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-[#d3d7d9] bg-white p-5 text-[13px] text-[#4a5560]">
        <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          Page-type checklist
        </div>
        <p className="mt-1.5 font-semibold text-[#0a0c0f]">
          No dedicated checklist for {pageTypeName ? pageTypeName.toLowerCase() : "this page type"}.
        </p>
        <p className="mt-1">
          Dedicated checklists apply to <strong>Service</strong>, <strong>Location</strong>, <strong>Category</strong>, and <strong>Homepage</strong> pages
          {pageTypeKey ? ` (this page was classified as “${pageTypeKey}”)` : ""}.
        </p>
      </div>
    );
  }

  const needed = items.filter((i) => i.status === "needed").length;
  const check = items.filter((i) => i.status === "check").length;
  const done = items.filter((i) => i.status === "done").length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[#ececec] bg-white px-4 py-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            {pageTypeName ?? "Page"} checklist
          </div>
          <p className="mt-0.5 text-[13px] text-[#4a5560]">
            Ordered by <strong className="text-[#0a0c0f]">{FOCUS_LABEL[focus ?? "visibility"]}</strong> focus and current page facts.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {needed > 0 ? <Pill t="miss">{needed} needed</Pill> : null}
          {check > 0 ? <Pill t="warn">{check} to check</Pill> : null}
          <Pill t="ok">{done} done</Pill>
        </div>
      </div>

      <ul className="space-y-2.5">
        {items.map((item) => {
          const st = STATUS_META[item.status] ?? STATUS_META.check;
          return (
            <li
              key={item.id}
              className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Pill t={st.tone}>{st.label}</Pill>
                    <Pill t="info">{item.category}</Pill>
                    {item.benefit ? <Pill t="lime">{item.benefit}</Pill> : null}
                  </div>
                  <h3 className="mt-2 font-[var(--font-heading)] text-[15px] font-bold text-[#0a0c0f]">
                    {item.title}
                  </h3>
                </div>
                <span className="shrink-0 text-[11px] font-medium text-[#7a838c]">
                  {item.action_type}
                </span>
              </div>

              {item.why ? (
                <p className="mt-1 text-[13px] text-[#4a5560]">{item.why}</p>
              ) : null}

              {item.steps.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {item.steps.map((step, idx) => (
                    <div key={`${item.id}-step-${idx}`} className="flex items-start gap-2.5 text-[13px] text-[#171a22]">
                      <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[#223540] text-[11px] font-bold text-white">
                        {idx + 1}
                      </span>
                      <span>{step}</span>
                    </div>
                  ))}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
