"use client";

import type { ChecklistItem } from "@/lib/engine";

const STATUS_META: Record<
  ChecklistItem["status"],
  { label: string; badgeClass: string; dotClass: string }
> = {
  done: {
    label: "Done",
    badgeClass: "bg-[#e9fedc] text-[#2f5a00]",
    dotClass: "bg-[#2f5a00]",
  },
  needed: {
    label: "Needed",
    badgeClass: "bg-[oklch(0.965_0.025_25)] text-[oklch(0.48_0.17_25)]",
    dotClass: "bg-[oklch(0.48_0.17_25)]",
  },
  check: {
    label: "Check",
    badgeClass: "bg-[oklch(0.97_0.045_85)] text-[oklch(0.42_0.1_65)]",
    dotClass: "bg-[oklch(0.68_0.16_65)]",
  },
};

export function ChecklistPanel({
  checklist,
  pageTypeName,
  focusOrderReason,
}: {
  checklist: ChecklistItem[] | undefined;
  pageTypeName?: string | null;
  focusOrderReason?: string | null;
}) {
  if (!checklist || checklist.length === 0) return null;

  const neededCount = checklist.filter((i) => i.status === "needed").length;
  const checkCount = checklist.filter((i) => i.status === "check").length;
  const doneCount = checklist.filter((i) => i.status === "done").length;

  return (
    <div className="rounded-xl border border-[#ececec] bg-white p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
            Page-type checklist{pageTypeName ? ` · ${pageTypeName}` : ""}
          </div>
          {focusOrderReason ? (
            <p className="mt-1 text-xs text-[#4a5560]">{focusOrderReason}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-semibold">
          {neededCount > 0 ? (
            <span className="rounded-full bg-[oklch(0.965_0.025_25)] px-2.5 py-0.5 text-[oklch(0.48_0.17_25)]">
              {neededCount} needed
            </span>
          ) : null}
          {checkCount > 0 ? (
            <span className="rounded-full bg-[oklch(0.97_0.045_85)] px-2.5 py-0.5 text-[oklch(0.42_0.1_65)]">
              {checkCount} to check
            </span>
          ) : null}
          {doneCount > 0 ? (
            <span className="rounded-full bg-[#e9fedc] px-2.5 py-0.5 text-[#2f5a00]">
              {doneCount} done
            </span>
          ) : null}
        </div>
      </div>

      <ul className="mt-3 space-y-2.5">
        {checklist.map((item) => {
          const meta = STATUS_META[item.status] ?? STATUS_META.check;
          return (
            <li
              key={item.id}
              className="rounded-[10px] border border-[#ececec] bg-[#f8f8f8] px-3.5 py-3"
            >
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${meta.badgeClass}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${meta.dotClass}`} />
                      {meta.label}
                    </span>
                    <span className="rounded-full bg-[#f1f3f4] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#4a5560]">
                      {item.category}
                    </span>
                    {item.benefit ? (
                      <span className="rounded-full bg-[#e6f7f5] px-2 py-0.5 text-[10px] font-semibold text-[#00665f]">
                        {item.benefit}
                      </span>
                    ) : null}
                  </div>
                  <h4 className="mt-1.5 font-[var(--font-heading)] text-sm font-bold text-[#0a0c0f]">
                    {item.title}
                  </h4>
                </div>
              </div>

              <p className="mt-1 text-[13px] text-[#4a5560]">{item.why}</p>

              {item.steps.length > 0 ? (
                <div className="mt-2.5 space-y-1.5">
                  {item.steps.map((step, idx) => (
                    <div key={idx} className="flex items-start gap-2.5 text-[13px] text-[#171a22]">
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
