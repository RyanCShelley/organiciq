"use client";

import { useRef, useState, useTransition } from "react";

import {
  createAnnotationAction,
  importAnnotationsAction,
  remeasureAnnotationsAction,
} from "@/app/(app)/annotation-actions";
import { Alert } from "@/components/ui/Alert";
import { FieldLabel, Input, Select } from "@/components/ui/Input";
import {
  ANNOTATION_CSV_TEMPLATE,
  ANNOTATION_TYPES,
  GROWTH_ACTIONS,
} from "@/lib/annotations";

export function AnnotationCreateForm({ clientId }: { clientId: string }) {
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  return (
    <form
      ref={formRef}
      className="space-y-4"
      action={(formData) => {
        setMessage(null);
        setError(null);
        startTransition(async () => {
          const result = await createAnnotationAction(formData);
          if (result.ok) {
            setMessage("Annotation saved.");
            formRef.current?.reset();
          } else {
            setError(result.error);
          }
        });
      }}
    >
      <input type="hidden" name="clientId" value={clientId} />
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <FieldLabel label="Date">
          <Input name="date" type="date" required />
        </FieldLabel>
        <FieldLabel label="Type">
          <Select name="annotation_type" defaultValue="growth_action" required>
            {ANNOTATION_TYPES.map((row) => (
              <option key={row.value} value={row.value}>
                {row.label}
              </option>
            ))}
          </Select>
        </FieldLabel>
        <FieldLabel label="Growth Action">
          <Select name="growth_action" defaultValue="">
            {GROWTH_ACTIONS.map((row) => (
              <option key={row.value || "none"} value={row.value}>
                {row.label}
              </option>
            ))}
          </Select>
        </FieldLabel>
        <FieldLabel label="Page URL" className="sm:col-span-2 lg:col-span-3">
          <Input name="page_url" type="url" placeholder="https://…" />
        </FieldLabel>
        <FieldLabel label="Description" className="sm:col-span-2 lg:col-span-3">
          <Input name="description" required placeholder="What changed?" />
        </FieldLabel>
        <FieldLabel label="Success metric">
          <Input name="success_metric" placeholder="e.g. CTR recovery" />
        </FieldLabel>
        <FieldLabel label="Completed">
          <Input name="completed_at" type="date" />
        </FieldLabel>
        <FieldLabel label="Measure from">
          <Input name="measurement_start_date" type="date" />
        </FieldLabel>
        <FieldLabel label="Measure to">
          <Input name="measurement_end_date" type="date" />
        </FieldLabel>
        <FieldLabel label="Notes" className="sm:col-span-2 lg:col-span-3">
          <Input name="notes" placeholder="Optional context" />
        </FieldLabel>
      </div>

      <button type="submit" className="btn btn-primary" disabled={pending}>
        {pending ? "Saving…" : "Add annotation"}
      </button>
    </form>
  );
}

export function AnnotationImportPanel({ clientId }: { clientId: string }) {
  const [pending, startTransition] = useTransition();
  const [csvText, setCsvText] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Array<{ row: number; error: string }>>([]);
  const fileRef = useRef<HTMLInputElement>(null);

  function downloadTemplate() {
    const blob = new Blob([ANNOTATION_CSV_TEMPLATE], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "organic-iq-annotations-template.csv";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn btn-ghost btn-sm" onClick={downloadTemplate}>
          Download CSV template
        </button>
        <label className="btn btn-ghost btn-sm cursor-pointer">
          Choose CSV file
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={async (event) => {
              const file = event.target.files?.[0];
              if (!file) return;
              setCsvText(await file.text());
              setMessage(null);
              setError(null);
              setRowErrors([]);
            }}
          />
        </label>
      </div>

      <FieldLabel label="CSV content">
        <textarea
          className="field-control min-h-[140px] font-mono text-xs"
          value={csvText}
          onChange={(event) => setCsvText(event.target.value)}
          placeholder="Paste historical annotations CSV here, or upload a file…"
        />
      </FieldLabel>

      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}
      {rowErrors.length > 0 ? (
        <Alert variant="warning">
          <p className="font-medium">Some rows failed:</p>
          <ul className="mt-1 list-disc pl-4 text-sm">
            {rowErrors.slice(0, 8).map((row) => (
              <li key={`${row.row}-${row.error}`}>
                Row {row.row}: {row.error}
              </li>
            ))}
          </ul>
        </Alert>
      ) : null}

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn btn-primary"
          disabled={pending || !csvText.trim()}
          onClick={() => {
            setMessage(null);
            setError(null);
            setRowErrors([]);
            const formData = new FormData();
            formData.set("clientId", clientId);
            formData.set("csv_text", csvText);
            startTransition(async () => {
              const result = await importAnnotationsAction(formData);
              if (result.ok) {
                setMessage(`Imported ${result.created} annotation${result.created === 1 ? "" : "s"}.`);
                setRowErrors(result.errors ?? []);
                if (result.created > 0) setCsvText("");
              } else {
                setError(result.error);
              }
            });
          }}
        >
          {pending ? "Importing…" : "Upload annotations"}
        </button>
        <form action={remeasureAnnotationsAction}>
          <input type="hidden" name="clientId" value={clientId} />
          <button type="submit" className="btn btn-ghost">
            Re-measure impact
          </button>
        </form>
      </div>

      <p className="text-xs text-[var(--text-secondary)]">
        Impact uses a light pre/post window (±5% meaningful change) from GA4/GSC when measurement
        dates are set, or from baseline_/post_ columns in the CSV.
      </p>
    </div>
  );
}
