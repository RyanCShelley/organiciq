"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { saveProfileAction } from "@/app/(app)/[clientSlug]/consulting/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { Profile } from "@/lib/portal";

const FIELDS: { key: keyof Profile; label: string; hint: string; internal?: boolean }[] = [
  { key: "primary_objective", label: "Primary performance objective", hint: "The one result that matters most, in their words." },
  { key: "goals", label: "Business goals", hint: "What the business wants over the next year." },
  { key: "audiences", label: "Target audiences", hint: "Who they sell to." },
  { key: "markets", label: "Markets", hint: "Where: cities, regions, countries." },
  { key: "priority_services", label: "Priority services or products", hint: "What to grow first." },
  { key: "constraints", label: "Known constraints", hint: "Budget, platform limits, approvals, seasonality." },
  { key: "editorial_rules", label: "Brand and editorial rules", hint: "Voice, words to avoid, claims they cannot make." },
  { key: "resources", label: "Who can implement", hint: "The developers, writers and time their team has." },
  { key: "internal_notes", label: "Internal notes", hint: "Only SMA sees these. They never appear in the client portal.", internal: true },
];

/** The consultant's workspace for one client: Understand, written once and kept current. Later steps (Measure to Follow through) join it here. */
export function ConsultingWorkspace({ client, profile, error }: { client: Client; profile: Profile | null; error: string | null }) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(FIELDS.map((f) => [f.key, (profile?.[f.key] as string | null) ?? ""])));
  const [aiFocus, setAiFocus] = useState(!!profile?.ai_visibility_focus);
  const [pending, start] = useTransition();
  const [saved, setSaved] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const save = () =>
    start(async () => {
      const r = await saveProfileAction(client.id, client.slug, { ...values, ai_visibility_focus: aiFocus } as Record<string, unknown>);
      if (r.ok) { setSaved(true); setProblem(null); } else setProblem(r.error);
    });
  return (
    <section className="max-w-3xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Consulting workspace</h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">{client.client_name}{client.group_name ? ` · ${client.group_name}` : ""}. Start with what you know about the business. The rest of the consulting steps join this page as they are built.</p>
        </div>
        <div className="flex gap-2"><Link href={`/${client.slug}/consulting/report`} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white">Report</Link><Link href={`/${client.slug}/consulting/recommendations`} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white">Recommendations</Link><Link href={`/consulting/${client.slug}`} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold text-[var(--brand-teal)] hover:underline">Preview as client</Link></div>
      </header>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      <div className="space-y-4 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
        <h2 className="text-lg font-bold">1. Understand</h2>
        <label className="flex items-start gap-2 text-sm font-semibold">
          <input type="checkbox" checked={aiFocus} onChange={(e) => { setAiFocus(e.target.checked); setSaved(false); }} className="mt-1" />
          <span>AI visibility is a focus for this client<span className="block text-xs font-normal text-[var(--text-secondary)]">Major AI-readiness (GEO) findings from site health are then put first when drafting recommendations.</span></span>
        </label>
        {FIELDS.map((f) => (
          <label key={f.key} className="block text-sm font-semibold">
            {f.label}{f.internal ? <span className="ml-2 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-semibold text-amber-900">Internal</span> : null}
            <span className="block text-xs font-normal text-[var(--text-secondary)]">{f.hint}</span>
            <textarea value={values[f.key]} onChange={(e) => { setValues({ ...values, [f.key]: e.target.value }); setSaved(false); }} rows={f.key === "primary_objective" ? 2 : 3} className="mt-1 w-full rounded-lg border border-[var(--border)] bg-white p-3 text-sm font-normal" />
          </label>
        ))}
        <div className="flex items-center gap-3">
          <button type="button" onClick={save} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">{pending ? <><Spinner />Saving…</> : "Save"}</button>
          {saved ? <span className="text-sm text-green-800">Saved{profile?.updated_by ? "" : ""}.</span> : null}
          {problem ? <span role="alert" className="text-sm text-red-800">{problem}</span> : null}
        </div>
      </div>
    </section>
  );
}
