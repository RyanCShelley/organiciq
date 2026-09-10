"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition, type MouseEvent } from "react";

import { deleteClientAction } from "@/app/(app)/client-actions";

export function DeleteClientButton({
  clientId,
  clientName,
}: {
  clientId: string;
  clientName: string;
}) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function onDelete(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setError(null);

    const confirmed = window.confirm(
      `Delete “${clientName}” and all of its synced data, integrations, and jobs?\n\nThis cannot be undone.`,
    );
    if (!confirmed) return;

    const formData = new FormData();
    formData.set("clientId", clientId);
    formData.set("clientName", clientName);

    startTransition(async () => {
      const result = await deleteClientAction(formData);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      router.refresh();
    });
  }

  return (
    <span className="inline-flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={onDelete}
        disabled={pending}
        className="btn btn-sm btn-ghost text-[var(--danger)] hover:bg-[var(--danger-soft)] hover:text-[var(--danger)]"
      >
        {pending ? "Deleting…" : "Delete"}
      </button>
      {error ? (
        <span className="text-[11px] text-[var(--danger)]">{error}</span>
      ) : null}
    </span>
  );
}
