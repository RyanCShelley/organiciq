"use client";

import { Fragment, useState } from "react";

import { formatDay, type Candidate } from "@/lib/monthly-record";

function path(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

type Kind = "page" | "term";

const COLUMNS: Record<Kind, { first: string; second?: string; score: string }> = {
  page: { first: "Page", second: "What it needs", score: "Impressions at stake" },
  term: { first: "Term", score: "Opportunity" },
};

/**
 * What the engine weighed and the plan had no room for, one row each.
 *
 * A row opens to the same facts a slotted card carries: why it was found, the
 * evidence behind it, the steps and what it would be judged on, plus the reason
 * it was left out. Seeing that is how a plan gets argued with.
 */
export function CandidateTable({
  rows,
  kind,
  limit = 25,
}: {
  rows: Candidate[];
  kind: Kind;
  limit?: number;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const columns = COLUMNS[kind];
  const width = columns.second ? 4 : 3;

  return (
    <div className="table-shell overflow-x-auto">
      <table>
        <thead>
          <tr>
            <th className="w-8" aria-label="Expand" />
            <th>{columns.first}</th>
            {columns.second ? <th>{columns.second}</th> : null}
            <th className="text-right">{columns.score}</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, limit).map((row) => {
            const isOpen = open === row.action_uid;
            const panelId = `candidate-${row.action_uid}`;
            return (
              <Fragment key={row.action_uid}>
                <tr
                  className="cursor-pointer hover:bg-[var(--surface-muted)]"
                  onClick={() => setOpen(isOpen ? null : row.action_uid)}
                >
                  <td className="text-[var(--text-tertiary)]">
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-controls={panelId}
                      aria-label={`${isOpen ? "Hide" : "Show"} detail for ${
                        row.term ?? row.title
                      }`}
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpen(isOpen ? null : row.action_uid);
                      }}
                      className="flex h-6 w-6 items-center justify-center rounded"
                    >
                      <span aria-hidden>{isOpen ? "▾" : "▸"}</span>
                    </button>
                  </td>
                  {kind === "page" ? (
                    <>
                      <td className="font-[family-name:var(--font-mono)] text-[12.5px]">
                        {path(row.target_url)}
                      </td>
                      <td className="text-[13px]">{row.title}</td>
                    </>
                  ) : (
                    <td className="text-[13px]">{row.term ?? row.title}</td>
                  )}
                  <td className="whitespace-nowrap text-right tabular-nums">
                    {Math.round(row.score).toLocaleString()}
                  </td>
                </tr>
                {isOpen ? (
                  <tr id={panelId}>
                    <td />
                    <td colSpan={width - 1} className="pb-4 pt-1">
                      <Detail row={row} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Detail({ row }: { row: Candidate }) {
  return (
    <div className="space-y-3 text-[13px] leading-relaxed text-[var(--text-secondary)]">
      {row.not_slotted_because ? (
        <p>
          <span className="font-semibold text-[var(--text-primary)]">Not in the plan: </span>
          {row.not_slotted_because}
        </p>
      ) : null}
      <p>
        <span className="font-semibold text-[var(--text-primary)]">{row.title}. </span>
        {row.why}
      </p>

      {row.evidence && row.evidence.length > 0 ? (
        <div>
          <p className="font-semibold text-[var(--text-primary)]">Evidence</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {row.evidence.map((line) => (
              <li key={line} className="font-[family-name:var(--font-mono)] text-[12px]">
                {line}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {row.steps && row.steps.length > 0 ? (
        <div>
          <p className="font-semibold text-[var(--text-primary)]">Steps</p>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5">
            {row.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
        </div>
      ) : null}

      <p>
        <span className="font-semibold text-[var(--text-primary)]">Done when: </span>
        {row.done_when}
      </p>

      <dl className="flex flex-wrap gap-x-6 gap-y-1">
        <div className="flex gap-1.5">
          <dt className="text-[var(--text-tertiary)]">Effort</dt>
          <dd className="font-semibold">{row.effort_min} min</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-[var(--text-tertiary)]">Measured by</dt>
          <dd className="font-semibold">{row.metric}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-[var(--text-tertiary)]">Check on</dt>
          <dd className="font-semibold">{formatDay(row.check_on)}</dd>
        </div>
        <div className="flex gap-1.5">
          <dt className="text-[var(--text-tertiary)]">Action</dt>
          <dd className="font-semibold">{row.id}</dd>
        </div>
      </dl>
    </div>
  );
}
