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
    <div className="mt-3">
      <button
        type="button"
        onClick={onDelete}
        disabled={pending}
        className="text-sm text-red-600 hover:text-red-700 disabled:opacity-60"
      >
        {pending ? "Deleting…" : "Delete client"}
      </button>
      {error ? <p className="mt-1 text-xs text-red-600">{error}</p> : null}
    </div>
  );
}
