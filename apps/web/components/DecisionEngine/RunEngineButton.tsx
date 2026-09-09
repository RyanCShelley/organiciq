"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { runDecisionEngineAction } from "@/app/(app)/actions";

export function RunEngineButton({
  clientId,
  from,
  to,
}: {
  clientId: string;
  from: string;
  to: string;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  function onClick() {
    setError(null);
    const formData = new FormData();
    formData.set("clientId", clientId);
    formData.set("from", from);
    formData.set("to", to);
    startTransition(async () => {
      try {
        await runDecisionEngineAction(formData);
        router.refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to run Decision Engine");
      }
    });
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        className="btn btn-primary btn-sm disabled:opacity-50"
        disabled={pending}
        onClick={onClick}
      >
        {pending ? "Running…" : "Run Engine"}
      </button>
      {error ? <span className="max-w-xs text-xs text-[var(--danger)]">{error}</span> : null}
    </div>
  );
}
