"use client";

import { useState, useTransition } from "react";

import { engineInputCoverageAction, type EngineInputCoverage } from "@/app/(app)/baseline-actions";
import { Alert } from "@/components/ui/Alert";

/**
 * Which mapped pages the decision engine could not read, per client, and which saved
 * actions were built on one. Read-only: it changes nothing.
 */
export function EngineInputCheckPanel() {
  const [pending, startTransition] = useTransition();
  const [report, setReport] = useState<EngineInputCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  function check() {
    setError(null);
    startTransition(async () => {
      const result = await engineInputCoverageAction();
      if (!result.ok) return setError(result.error);
      setReport(result.report);
    });
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-[var(--text-secondary)]">
        The visibility actions judge a page from the site crawl. A mapped page the crawl could not read as a normal page
        (a redirecting URL, an error, a crawl from before headings were captured, or a URL the crawl never reached) is
        unknown to the engine, not empty. This lists those pages and any saved action that rests on one, so its plan can
        be re-run.
      </p>
      <button type="button" className="btn btn-secondary" disabled={pending} onClick={check}>
        {pending ? "Checking…" : "Check mapped pages"}
      </button>
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {report ? (
        <div className="space-y-4">
          <p className="text-sm">
            {report.totals.needing_attention} of {report.totals.targets} mapped pages across {report.totals.clients}{" "}
            clients need attention; {report.totals.affected_actions} saved action
            {report.totals.affected_actions === 1 ? "" : "s"} rest on one.
          </p>
          {report.clients
            .filter((row) => row.problems.length > 0)
            .map((row) => (
              <div key={row.client_id} className="space-y-1.5 border-t border-[var(--border)] pt-3">
                <p className="text-sm font-semibold">
                  {row.client_name}{" "}
                  <span className="font-normal text-[var(--text-tertiary)]">
                    · {row.problems.length} of {row.targets} mapped pages · crawl {row.crawl_date ?? "none"}
                  </span>
                </p>
                <ul className="space-y-1 text-xs text-[var(--text-secondary)]">
                  {row.problems.map((problem) => (
                    <li key={`${problem.keyword}-${problem.target_url}`}>
                      <span className="font-medium text-[var(--text-primary)]">{problem.keyword}</span> →{" "}
                      {problem.target_url}: {problem.detail}
                      {problem.http_status ? ` (HTTP ${problem.http_status})` : ""}
                    </li>
                  ))}
                </ul>
                {row.affected_actions.length > 0 ? (
                  <p className="text-xs text-[#8A4B08]">
                    Re-run {row.affected_actions[0].month}:{" "}
                    {row.affected_actions.map((action) => `${action.id} on ${action.target_url}`).join("; ")}
                  </p>
                ) : null}
              </div>
            ))}
          {report.totals.needing_attention === 0 ? (
            <p className="text-sm text-[var(--text-secondary)]">Every mapped page was read.</p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
