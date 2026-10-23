"use client";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import { runMonthlyRecordAction } from "@/app/(app)/[clientSlug]/decision-engine/actions";
import { clientHref } from "@/lib/client-path";
export function SetupFinishButton({ clientId, slug, ready, alreadyRun }: { clientId: string; slug: string; ready: boolean; alreadyRun: boolean }) {
  const [pending, startTransition] = useTransition(); const [error, setError] = useState<string | null>(null); const router = useRouter();
  return <div className="space-y-3"><p className="text-sm text-[var(--text-secondary)]">The first assessment uses the saved configuration. It does not approve growth actions, send Teamwork tasks or lock a baseline.</p>
    <button className="btn btn-primary" disabled={!ready || pending} onClick={() => startTransition(async () => {
      setError(null);
      if (alreadyRun) { router.push(clientHref(slug)); return; }
      const result = await runMonthlyRecordAction(clientId, slug);
      if (!result.ok) { setError(result.error); return; }
      router.refresh(); router.push(`/${slug}/decision-engine?run=${encodeURIComponent(result.month)}`);
    })}>{pending ? "Running assessment…" : alreadyRun ? "Finish setup" : "Finish setup & run first assessment"}</button>
    {!ready ? <p className="text-sm text-[var(--text-secondary)]">Finish the required stages above before running the assessment. Goals and baseline can be reviewed later.</p> : null}
    {error ? <p role="alert" className="text-sm text-red-700">{error}</p> : null}
  </div>;
}
