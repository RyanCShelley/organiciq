"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { createSitesAction, type SiteResult } from "@/app/(app)/new-client/actions";
import { Card, Field, inputClass } from "@/components/ui/form";
import { Spinner } from "@/components/ui/Spinner";
import type { Tier } from "@/lib/clients";

/** "Name, domain" or just "domain" per line; a bare domain becomes its name without www and the ending. */
export function parseSites(text: string): { name: string; domain: string }[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((line) => {
      const [first, second] = line.split(/[,\t]/).map((p) => p.trim());
      const domain = (second || first).replace(/^https?:\/\//, "").replace(/\/.*$/, "");
      const base = domain.replace(/^www\./, "").split(".")[0];
      return { name: second ? first : base.charAt(0).toUpperCase() + base.slice(1), domain };
    });
}

export function AddSitesForm({ tiers }: { tiers: Tier[] }) {
  const [pending, start] = useTransition();
  const [group, setGroup] = useState("");
  const [mode, setMode] = useState<"execution" | "consulting">("consulting");
  const [tierId, setTierId] = useState("");
  const [text, setText] = useState("");
  const [results, setResults] = useState<SiteResult[] | null>(null);
  const sites = parseSites(text);
  const run = () => start(async () => setResults(await createSitesAction(group.trim(), mode, sites, mode === "execution" ? tierId : null)));
  return (
    <Card>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Group" hint="The company these sites belong to, such as Flint.">
          <input value={group} onChange={(e) => setGroup(e.target.value)} className={inputClass} />
        </Field>
        <Field label="How we work with them">
          <select value={mode} onChange={(e) => setMode(e.target.value as "execution" | "consulting")} className={inputClass}>
            <option value="consulting">Consulting: advisory portal; their team does the work</option>
            <option value="execution">Execution: we do the work</option>
          </select>
        </Field>
        {mode === "execution" ? (
          <Field label="OrganicIQ tier">
            <select value={tierId} onChange={(e) => setTierId(e.target.value)} className={inputClass}>
              <option value="" disabled>Choose a tier</option>
              {tiers.map((t) => <option key={t.id} value={t.id}>{t.tier_name}</option>)}
            </select>
          </Field>
        ) : null}
      </div>
      <Field label="The sites" hint="One per line: a domain, or a name, then a comma, then the domain.">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={8} placeholder={"flintroofing.com\nFlint North, north.flintexample.com"} className={`${inputClass} font-mono`} />
      </Field>
      <div className="mt-4 flex items-center gap-3">
        <button type="button" onClick={run} disabled={pending || sites.length === 0 || !group.trim() || (mode === "execution" && !tierId)} className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {pending ? <><Spinner />Adding…</> : `Add ${sites.length || ""} site${sites.length === 1 ? "" : "s"}`}
        </button>
        <span className="text-sm text-[var(--text-secondary)]">Each site becomes its own client. Search Console and Analytics are connected from each one&apos;s Connections.</span>
      </div>
      {results ? (
        <ul className="mt-4 space-y-1 text-sm">
          {results.map((r) => (
            <li key={r.line} className={r.ok ? "text-green-800" : "text-red-800"}>
              {r.ok ? "✓ " : "✕ "}
              {r.ok && r.slug ? <Link href={`/${r.slug}/settings`} className="underline">{r.line}</Link> : r.line}
              {r.error ? `: ${r.error}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
