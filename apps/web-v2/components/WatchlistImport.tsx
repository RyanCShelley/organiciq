"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { importWatchlistAction } from "@/app/(app)/[clientSlug]/watchlist/actions";
import type { ImportReport } from "@/lib/watchlist";

export function WatchlistImport({ clientId, slug }: { clientId: string; slug: string }) {
  const router = useRouter();
  const [csvText, setCsvText] = useState("");
  const [fileName, setFileName] = useState("");
  const [report, setReport] = useState<ImportReport | null>(null);
  const [error, setError] = useState("");
  const [pending, startTransition] = useTransition();

  function run(dryRun: boolean) {
    setError("");
    startTransition(async () => {
      const result = await importWatchlistAction(clientId, slug, csvText, dryRun);
      if (!result.ok) {
        setReport(null);
        setError(result.error);
        return;
      }
      setReport(result.report);
      if (!dryRun) router.refresh();
    });
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <h2 className="text-sm font-semibold">Import from CSV</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Export the Watchlist tab as CSV. Rows are added or updated by keyword; nothing is deleted
        and blank cells never erase what is stored.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <label className={`flex min-w-0 cursor-pointer items-center gap-3 rounded-lg border-2 border-dashed px-4 py-3 text-sm focus-within:ring-2 focus-within:ring-[var(--brand-teal)] ${fileName ? "border-[var(--brand-teal)] bg-teal-50" : "border-[var(--brand-teal)] bg-white hover:bg-teal-50"}`}>
          <span className="shrink-0 rounded-lg bg-[var(--brand-dark)] px-4 py-2 font-semibold text-white">{fileName ? "Choose a different file" : "Choose CSV file"}</span>
          <span className="truncate font-medium">{fileName || "No file chosen yet"}</span>
          <input
            type="file"
            accept=".csv,text/csv"
            aria-label="Watchlist CSV"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              setReport(null);
              setError("");
              setFileName(file?.name ?? "");
              setCsvText(file ? await file.text() : "");
            }}
            className="sr-only"
          />
        </label>
        <button
          type="button"
          className="btn border border-[var(--border)] px-4 py-2"
          disabled={!csvText || pending}
          onClick={() => run(true)}
        >
          Preview
        </button>
        <button
          type="button"
          className="btn btn-primary px-4 py-2"
          disabled={!csvText || pending}
          onClick={() => run(false)}
        >
          Import
        </button>
      </div>

      {error ? (
        <p role="alert" className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      {report ? <Report report={report} fileName={fileName} /> : null}
    </div>
  );
}

function Report({ report, fileName }: { report: ImportReport; fileName: string }) {
  return (
    <div className="mt-4 space-y-3 text-sm" aria-live="polite">
      <p className="font-semibold">
        {report.dry_run ? "Preview, nothing saved" : "Imported"} · {fileName}
      </p>
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Rows read" value={report.rows_read} />
        <Stat label="New buckets" value={report.buckets_created} />
        <Stat label="New keywords" value={report.keywords_created} />
        <Stat label="Updated" value={report.keywords_updated} />
      </ul>
      {report.topics_inherited > 0 ? (
        <p className="text-[var(--text-secondary)]">
          {report.topics_inherited} rows had no topic and took the one above them (merged cells in
          the sheet). Check that is right.
        </p>
      ) : null}
      {report.ignored_columns.length > 0 ? (
        <p className="text-[var(--text-secondary)]">
          Not imported: {report.ignored_columns.join(", ")}
        </p>
      ) : null}
      <Issues title="Skipped rows" issues={report.skipped} />
      <Issues title="Warnings" issues={report.warnings} />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <li className="rounded-lg bg-[var(--background)] px-3 py-2">
      <div className="text-xl font-bold">{value}</div>
      <div className="text-xs text-[var(--text-secondary)]">{label}</div>
    </li>
  );
}

function Issues({
  title,
  issues,
}: {
  title: string;
  issues: { line: number; keyword?: string; reason: string }[];
}) {
  if (issues.length === 0) return null;
  return (
    <div>
      <p className="font-semibold">{title}</p>
      <ul className="mt-1 list-disc pl-5 text-[var(--text-secondary)]">
        {issues.map((issue, index) => (
          <li key={index}>
            Line {issue.line}
            {issue.keyword ? ` (${issue.keyword})` : ""}: {issue.reason}
          </li>
        ))}
      </ul>
    </div>
  );
}
