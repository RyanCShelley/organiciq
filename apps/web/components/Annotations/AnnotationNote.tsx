"use client";

import { useState, useTransition } from "react";

import { updateAnnotationNoteAction } from "@/app/(app)/annotation-actions";

/** The note on one history entry: read where it sits, edited in place. */
export function AnnotationNote({
  clientId,
  id,
  notes,
}: {
  clientId: string;
  id: string;
  notes: string | null;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function save() {
    setError(null);
    startTransition(async () => {
      const result = await updateAnnotationNoteAction({ clientId, id, notes: draft });
      if (result.ok) setEditing(false);
      else setError(result.error);
    });
  }

  if (!editing) {
    return (
      <div className="mt-1.5 text-xs">
        {notes ? <p className="whitespace-pre-wrap text-[var(--text-secondary)]">{notes}</p> : null}
        <button
          type="button"
          onClick={() => {
            setDraft(notes ?? "");
            setEditing(true);
          }}
          className="font-semibold text-[var(--brand-teal-hover)] underline"
        >
          {notes ? "Edit note" : "Add a note"}
        </button>
      </div>
    );
  }

  return (
    <div className="mt-1.5 space-y-1.5">
      <textarea
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        rows={3}
        aria-label="Note"
        className="w-full rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-2.5 py-1.5 text-xs"
      />
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={pending}
          onClick={save}
          className="rounded-lg border border-[var(--border)] px-2.5 py-1 text-xs font-semibold disabled:opacity-60"
        >
          {pending ? "Saving…" : "Save note"}
        </button>
        <button
          type="button"
          disabled={pending}
          onClick={() => setEditing(false)}
          className="text-xs text-[var(--text-secondary)] underline"
        >
          Cancel
        </button>
        {error ? (
          <span role="alert" className="text-xs text-[#B4441C]">
            {error}
          </span>
        ) : null}
      </div>
    </div>
  );
}
