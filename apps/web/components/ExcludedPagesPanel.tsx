"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Alert } from "@/components/ui/Alert";
import { FieldLabel, Input } from "@/components/ui/Input";

export type ExcludedPage = { url_pattern: string; reason: string };

const BLANK: ExcludedPage = { url_pattern: "", reason: "" };

/**
 * Pages the engine must leave alone.
 *
 * The table has existed as long as the engine and nothing could write to it,
 * so "we are not working on careers" was a thing somebody could say and not
 * record — and Boys Electrical's only traffic action was on /careers.
 *
 * A reason is required. An exclusion with none is a rule nobody can review,
 * and next year nobody will remember why the engine stopped looking at a
 * section of the site.
 */
export function ExcludedPagesPanel({
  clientId,
  initial,
}: {
  clientId: string;
  initial: ExcludedPage[];
}) {
  const router = useRouter();
  const [rows, setRows] = useState<ExcludedPage[]>(
    initial.length > 0 ? initial : [BLANK],
  );
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function update(index: number, patch: Partial<ExcludedPage>) {
    setSaved(false);
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function save() {
    setError(null);
    setSaved(false);
    const pages = rows.filter((row) => row.url_pattern.trim());
    startTransition(async () => {
      const res = await fetch("/api/proxy/excluded-pages", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId, pages }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setError(body.detail || "Those did not save");
        return;
      }
      setSaved(true);
      router.refresh();
    });
  }

  return (
    <div className="space-y-4">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {saved ? (
        <Alert variant="success">
          Saved. The next run will not prescribe for these.
        </Alert>
      ) : null}

      <div className="space-y-3">
        {rows.map((row, index) => (
          <div
            key={index}
            className="grid gap-3 rounded-lg border border-[var(--border)] p-4 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_auto]"
          >
            <FieldLabel label="Page or section">
              <Input
                value={row.url_pattern}
                placeholder="/careers*"
                onChange={(e) => update(index, { url_pattern: e.target.value })}
              />
            </FieldLabel>
            <FieldLabel label="Why">
              <Input
                value={row.reason}
                placeholder="Not a focus this year"
                onChange={(e) => update(index, { reason: e.target.value })}
              />
            </FieldLabel>
            <button
              type="button"
              className="btn btn-secondary self-end"
              onClick={() => {
                setSaved(false);
                setRows((prev) =>
                  prev.length === 1 ? [BLANK] : prev.filter((_, i) => i !== index),
                );
              }}
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => setRows((prev) => [...prev, BLANK])}
        >
          Add a page
        </button>
        <button
          type="button"
          className="btn btn-primary"
          onClick={save}
          disabled={pending}
        >
          {pending ? "Saving…" : "Save"}
        </button>
        {/* A trailing * is the difference between one page and a section,
            and it is not guessable from the field. */}
        <p className="text-xs text-[var(--text-tertiary)]">
          A trailing <code>*</code> takes the section: <code>/careers*</code> covers
          the index and everything under it.
        </p>
      </div>
    </div>
  );
}
