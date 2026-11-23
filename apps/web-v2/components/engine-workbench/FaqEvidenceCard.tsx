"use client";

import Link from "next/link";

import type { GrowthPart, Winners } from "@/lib/engine";
import { Pill, shortPage } from "@/components/engine-workbench/tokens";

export function FaqEvidenceCard({
  questions,
  serpQuestions,
  fq1Part,
  clientSlug,
  pageUrl,
}: {
  questions: NonNullable<Winners["comparison"]["questions"]> | null | undefined;
  serpQuestions: string[];
  fq1Part: GrowthPart | null | undefined;
  clientSlug: string;
  pageUrl: string;
}) {
  const missing = questions?.missing ?? [];
  const checked = questions?.checked ?? 0;
  const answered = Math.max(0, checked - missing.length);

  // Merge any DataForSEO PAA questions not already listed in missing
  const missingNorm = new Set(missing.map((m) => m.question.trim().toLowerCase()));
  const extraPaa = serpQuestions.filter((q) => !missingNorm.has(q.trim().toLowerCase()));

  if (!questions && extraPaa.length === 0 && !fq1Part) return null;

  return (
    <div className="rounded-xl border border-[#ececec] bg-white px-[18px] py-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[#7a838c]">
          FAQ &amp; People Also Ask coverage
        </span>
        {questions ? (
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill t="ok">{answered} answered</Pill>
            <Pill t={missing.length > 0 ? "warn" : "ok"}>{missing.length} missing</Pill>
            <Pill t="info">{checked} checked</Pill>
          </div>
        ) : null}
      </div>

      {fq1Part ? (
        <div className="mt-3 rounded-[10px] border border-[#bfe9e4] bg-[#eef8f7] px-3.5 py-2.5 text-[13px]">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              <Pill t="ok">Site FAQ page found</Pill>
              <strong className="text-[#0a0c0f]">{fq1Part.title}</strong>
            </div>
            <Link
              href={`/${clientSlug}/inlinks?target=${encodeURIComponent(pageUrl)}`}
              className="text-xs font-semibold text-[#00857b] hover:underline"
            >
              Open Inlink suggester →
            </Link>
          </div>
          <p className="mt-1 text-xs text-[#4a5560]">{fq1Part.why}</p>
          {fq1Part.steps[0] ? (
            <p className="mt-1 text-xs font-semibold text-[#00665f]">{shortPage(fq1Part.steps[0])}</p>
          ) : null}
        </div>
      ) : null}

      {missing.length > 0 ? (
        <div className="mt-3">
          <div className="text-xs font-semibold text-[#0a0c0f]">
            Questions people ask that this page does not answer yet
          </div>
          <ul className="mt-2 space-y-2">
            {missing.map((q) => (
              <li key={q.question} className="rounded-[10px] border border-[#f1f2f3] bg-[#f8f8f8] px-3 py-2 text-[13px]">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-semibold text-[#0a0c0f]">“{q.question}”</span>
                  <Pill t="info">{q.source_name}</Pill>
                  {q.detail ? <span className="text-xs text-[#7a838c]">{q.detail}</span> : null}
                </div>
                {q.why ? <p className="mt-1 text-xs text-[#4a5560]">{q.why}</p> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : questions ? (
        <p className="mt-2 text-[13px] text-[#00665f]">
          All {checked} checked questions are already answered on this page.
        </p>
      ) : null}

      {extraPaa.length > 0 ? (
        <div className="mt-3">
          <div className="text-xs font-semibold text-[#0a0c0f]">
            People Also Ask on Google SERP ({extraPaa.length})
          </div>
          <ul className="mt-1.5 space-y-1 text-xs text-[#4a5560]">
            {extraPaa.map((q) => (
              <li key={q} className="flex items-start gap-2">
                <span className="font-bold text-[#00a99d]">?</span>
                <span>{q}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
