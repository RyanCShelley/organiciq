"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Fragment, useEffect, useState, useTransition } from "react";

import { addIgnoreAction, approveConceptAction, pageAction, removeConceptAction, removeIgnoreAction, searchConceptsAction, startPageReportAction } from "@/app/(app)/[clientSlug]/schema/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { ScCandidate, ScCategory, ScCheck, ScConcept, ScData, ScDepth, ScFinding, ScFindingGroup, ScIgnoreScope, ScItem, ScLayer, ScPage, ScReport, ScResponse, ScType } from "@/lib/schema";

type Ignore = (scope: ScIgnoreScope, key: string, label: string) => void;

const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const tone = (score: number) => (score >= 85 ? "#0f766e" : score >= 70 ? "#b45309" : "#b91c1c");
const DEPTH: Record<ScDepth, string> = { quick: "Quick (Sonnet 5.5)", deep: "Deep dive (Opus 5.5)", deepest: "Deepest (Fable 5.1)" };

const CATEGORY: Record<ScCategory, { label: string; plural: string; chip: string; hint: string }> = {
  error: { label: "Error", plural: "Errors", chip: "bg-[#fde8e4] text-[#b23a15]", hint: "Not real Schema.org. Fix." },
  warning: { label: "Warning", plural: "Warnings", chip: "bg-[#fdf1d3] text-[#8a5a00]", hint: "Something the page needs is missing, or the markup conflicts. Fix." },
  enhancement: { label: "Enhancement", plural: "Enhancements", chip: "bg-[#e7fedc] text-[#2f6b0d]", hint: "Would help. Nothing is wrong." },
  informational: { label: "Informational", plural: "Informational", chip: "bg-[#eceef2] text-[#4a5468]", hint: "Good to know." },
};
const LAYER: Record<ScLayer, string> = { schemaorg: "Schema.org", graph: "Entities", google: "Google Search", baseline: "SMA baseline", recommendation: "Recommendation" };

function Evidence({ value }: { value: unknown }) {
  if (value == null) return null;
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);
  return <pre className="mt-1 max-h-40 overflow-auto rounded-lg bg-[var(--bg)] p-2 text-[0.7rem] leading-snug">{text}</pre>;
}

function Badges({ f }: { f: Pick<ScFinding, "category" | "layer" | "confidence" | "auto_fixable"> }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5 text-[0.65rem] font-semibold uppercase tracking-wide">
      <span className={`rounded-full px-2 py-0.5 ${CATEGORY[f.category].chip}`}>{CATEGORY[f.category].label}</span>
      <span className="rounded-full bg-[var(--bg)] px-2 py-0.5 text-[var(--text-secondary)]">{LAYER[f.layer]}</span>
      {f.confidence !== "high" ? <span className="rounded-full bg-[var(--bg)] px-2 py-0.5 text-[var(--text-tertiary)]">{f.confidence} confidence</span> : null}
      {f.auto_fixable ? <span className="rounded-full bg-[var(--bg)] px-2 py-0.5 text-[var(--text-tertiary)]">fixable automatically</span> : null}
    </span>
  );
}

/** Everything the validator found, grouped by cause: the technical category first, then which layer found it, with the evidence from the markup. */
function Findings({ data, onOpen, onIgnore }: { data: ScData; onOpen: (url: string) => void; onIgnore: Ignore }) {
  const [category, setCategory] = useState<ScCategory>(data.finding_counts.error.groups ? "error" : data.finding_counts.warning.groups ? "warning" : "enhancement");
  const [layer, setLayer] = useState<ScLayer | "all">("all");
  const [openKey, setOpenKey] = useState<string | null>(null);
  const inCategory = data.findings.filter((g) => g.category === category);
  const shown = inCategory.filter((g) => layer === "all" || g.layer === layer);
  const layers = (["schemaorg", "graph", "google", "baseline", "recommendation"] as ScLayer[]).filter((l) => inCategory.some((g) => g.layer === l));
  return (
    <section className={card}>
      <h2 className="px-5 pt-4 text-lg font-bold">What the markup needs</h2>
      <p className="px-5 text-xs text-[var(--text-tertiary)]">
        Five checks: valid Schema.org (version {data.validator.schemaorg_version}), entities that agree, what Google Search features need (reviewed {data.validator.google_reviewed}), the SMA baseline, and what would add more.
        A property Google does not use is never an error.
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 px-5 sm:grid-cols-4" role="tablist" aria-label="Category">
        {(Object.keys(CATEGORY) as ScCategory[]).map((c) => {
          const n = data.finding_counts[c];
          return (
            <button key={c} type="button" role="tab" aria-selected={category === c} onClick={() => { setCategory(c); setLayer("all"); }} title={CATEGORY[c].hint}
              className={`rounded-xl border px-3 py-2 text-left ${category === c ? "border-[var(--brand-navy)] bg-white shadow-sm" : "border-[var(--border)] bg-[var(--bg)] hover:bg-white"}`}>
              <div className="text-xs font-semibold text-[var(--text-secondary)]">{CATEGORY[c].plural}</div>
              <div className="font-[family-name:var(--font-heading)] text-xl font-bold tabular-nums">{n.groups}</div>
              <div className="text-[0.7rem] text-[var(--text-tertiary)]">issue{n.groups === 1 ? "" : "s"} on {n.pages} page{n.pages === 1 ? "" : "s"}</div>
            </button>
          );
        })}
      </div>
      <p className="px-5 pt-2 text-xs text-[var(--text-secondary)]">{CATEGORY[category].hint}</p>
      {layers.length > 1 ? (
        <div className="flex flex-wrap gap-2 px-5 pt-2" role="group" aria-label="Which check found it">
          {(["all", ...layers] as (ScLayer | "all")[]).map((l) => (
            <button key={l} type="button" aria-pressed={layer === l} onClick={() => setLayer(l)} className={`rounded-full border px-3 py-1 text-xs font-semibold ${layer === l ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)]"}`}>
              {l === "all" ? "All" : LAYER[l]}
            </button>
          ))}
        </div>
      ) : null}
      {shown.length === 0 ? <p className="px-5 py-4 text-sm text-[var(--text-secondary)]">Nothing here.</p> : (
        <ul className="mt-2 divide-y divide-[var(--border)] px-5 pb-2">
          {shown.map((g) => (
            <li key={g.template_key} className="py-3">
              <div className="flex flex-wrap items-start gap-3">
                <span className="w-20 shrink-0 font-bold tabular-nums">{g.pages} page{g.pages === 1 ? "" : "s"}</span>
                <div className="min-w-0 flex-1">
                  <button type="button" onClick={() => setOpenKey(openKey === g.template_key ? null : g.template_key)} aria-expanded={openKey === g.template_key} className="text-left text-sm font-semibold hover:underline">{g.title}</button>
                  <div className="mt-1"><Badges f={g} /></div>
                </div>
                {g.category === "error" || g.category === "warning" ? (
                  <button type="button" onClick={() => onIgnore("cleanup", g.title, g.title)} className="text-xs text-[var(--text-tertiary)] underline">Ignore</button>
                ) : null}
              </div>
              {openKey === g.template_key ? (
                <div className="mt-2 space-y-2 pl-[5.75rem] text-sm">
                  <p>{g.explanation}</p>
                  <p><strong>What to do:</strong> {g.recommendation}</p>
                  <p className="text-xs text-[var(--text-secondary)]">On {shortPage(g.example.url)}: {g.example.message}</p>
                  <Evidence value={g.example.evidence} />
                  <div className="flex flex-wrap items-center gap-3 text-xs">
                    <a href={g.doc} target="_blank" rel="noreferrer" className="font-semibold text-[var(--brand-teal)] underline">Documentation</a>
                    <span className="text-[var(--text-tertiary)]">Rule {g.rule_id}</span>
                    {g.sample_urls.map((u) => <button key={u} type="button" onClick={() => onOpen(u)} className="font-semibold underline">{shortPage(u)}</button>)}
                    {g.pages > g.sample_urls.length ? <span className="text-[var(--text-tertiary)]">and {g.pages - g.sample_urls.length} more</span> : null}
                  </div>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Bar({ score }: { score: number }) {
  return (
    <div className="h-2 w-full rounded-full bg-[var(--border)]" aria-hidden>
      <div className="h-2 rounded-full" style={{ width: `${score}%`, background: tone(score) }} />
    </div>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={`${card} p-4`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {note ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{note}</div> : null}
    </div>
  );
}

/** A markup type with a small "not needed" cross: this client does not need it for this kind of page. */
function Chip({ label, onIgnore }: { label: string; onIgnore: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded bg-[var(--bg)] px-1.5 py-0.5 font-medium text-[var(--text-primary)]">
      {label}
      <button type="button" onClick={onIgnore} aria-label={`${label} is not needed`} title="Not needed for this client" className="text-[var(--text-tertiary)] hover:text-red-700">×</button>
    </span>
  );
}

function PageList({ title, items, total, onOpen, onIgnore }: { title: string; items: ScItem[]; total: number; onOpen: (url: string) => void; onIgnore: Ignore }) {
  if (total === 0) return null;
  return (
    <div className="mt-3">
      <div className="text-xs font-semibold">{title} ({total})</div>
      <ul className="mt-1 max-h-60 space-y-1.5 overflow-y-auto text-xs">
        {items.map((i) => (
          <li key={i.url} className="flex flex-wrap items-start gap-2">
            <button type="button" onClick={() => onOpen(i.url)} className="break-all text-left font-semibold underline">{shortPage(i.url)}</button>
            <span className="min-w-0 flex-1 text-[var(--text-secondary)]">{i.text}</span>
            <button type="button" onClick={() => onIgnore("page", i.url, `${shortPage(i.url)}: ignored`)} className="text-[var(--text-tertiary)] underline">Ignore</button>
          </li>
        ))}
        {total > items.length ? <li className="text-[var(--text-tertiary)]">and {total - items.length} more</li> : null}
      </ul>
    </div>
  );
}

function TypeRow({ t, onOpen, onIgnore }: { t: ScType; onOpen: (url: string) => void; onIgnore: Ignore }) {
  const [open, setOpen] = useState(false);
  const clean = t.affected === 0 && t.recommended_affected === 0 && (t.score == null || t.score >= 100);
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-[16rem] flex-1">
          <div className="font-semibold">{t.label} <span className="font-normal text-[var(--text-tertiary)]">· {t.pages} page{t.pages === 1 ? "" : "s"}</span></div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-[var(--text-secondary)]">
            {t.expects.length > 0 ? <span>Expected:</span> : <span>Nothing in particular is expected.</span>}
            {t.expects.map((x) => <Chip key={x} label={x} onIgnore={() => onIgnore("expect", `${t.page_type}:${x}`, `${t.label}: ${x} is not expected`)} />)}
            {t.recommended.length > 0 ? <span className="ml-1">Worth adding:</span> : null}
            {t.recommended.map((x) => <Chip key={x} label={x} onIgnore={() => onIgnore("expect", `${t.page_type}:${x}`, `${t.label}: ${x} is not wanted`)} />)}
            <button type="button" onClick={() => onIgnore("page_type", t.page_type, `${t.label}: ignored`)} className="ml-2 underline">Ignore this kind</button>
          </div>
        </div>
        {t.score != null ? (
          <>
            <div className="w-40"><Bar score={t.score} /></div>
            <div className="w-12 text-right text-sm font-bold tabular-nums">{t.score}</div>
          </>
        ) : <div className="w-52" />}
        <div className="flex w-64 justify-end text-xs">
          {clean ? <span className="font-semibold text-green-700">Clean</span> : (
            <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="text-right font-semibold underline">{open ? "Hide" : "See why it scored this way and how to fix it"}</button>
          )}
        </div>
      </div>
      {open ? (
        <div className="mt-2 rounded-lg bg-[var(--bg)] p-4 text-sm">
          <p className="font-semibold">{t.why.summary}</p>
          {t.why.should_have ? <p className="mt-1 text-xs text-[var(--text-secondary)]">{t.why.should_have}</p> : null}
          {t.why.gaps.length > 0 ? (
            <>
              <div className="mt-3 text-xs font-semibold">Why it lost points</div>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs text-[var(--text-secondary)]">{t.why.gaps.map((g) => <li key={g}>{g}</li>)}</ul>
            </>
          ) : null}
          {t.why.steps.length > 0 ? (
            <>
              <div className="mt-3 text-xs font-semibold">What to do</div>
              <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-xs text-[var(--text-secondary)]">{t.why.steps.map((g) => <li key={g}>{g}</li>)}</ol>
              {t.why.gain > 0 ? <p className="mt-2 text-xs text-[var(--text-secondary)]">Doing all of this would bring the score to 100.</p> : null}
            </>
          ) : null}
          <PageList title="Pages to fix" items={t.items} total={t.affected} onOpen={onOpen} onIgnore={onIgnore} />
          <PageList title="Pages that could add more markup" items={t.recommended_items} total={t.recommended_affected} onOpen={onOpen} onIgnore={onIgnore} />
        </div>
      ) : null}
    </li>
  );
}

/** One check. Every check opens: to what was found behind it and the pages that carry it, or, when nothing was found, to what to do about it. */
function CheckRow({ c, open, onToggle, onIgnore, onOpen, extra }: { c: ScCheck; open: boolean; onToggle: () => void; onIgnore: Ignore; onOpen: (url: string) => void; extra?: React.ReactNode }) {
  const clean = c.status === "pass";
  const ignored = c.status === "ignored";
  const optional = c.status === "optional";
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-start gap-3">
        <span className={`mt-0.5 w-14 shrink-0 text-xs font-semibold ${clean ? "text-green-700" : ignored || optional ? "text-[var(--text-tertiary)]" : c.status === "warn" ? "text-amber-700" : "text-red-700"}`}>{clean ? "Clean" : ignored ? "Ignored" : optional ? "Optional" : "To fix"}</span>
        <div className="min-w-0 flex-1">
          <button type="button" onClick={onToggle} aria-expanded={open} className={`flex items-center gap-1.5 text-left font-semibold ${ignored ? "text-[var(--text-tertiary)]" : ""}`}>
            <span aria-hidden className={`text-xs text-[var(--text-tertiary)] transition-transform ${open ? "rotate-90" : ""}`}>▸</span>
            {c.label}
            <span className="text-xs font-normal text-[var(--text-secondary)] underline">{open ? "Hide" : clean ? "See what was found" : "See what to do"}</span>
          </button>
          <div className="text-xs text-[var(--text-secondary)]">{c.detail}</div>
          {c.fix ? <div className="mt-0.5 text-xs font-medium">{c.fix}</div> : null}
        </div>
        {!clean && !ignored ? <button type="button" onClick={() => onIgnore("check", c.key, c.label)} className="text-xs text-[var(--text-tertiary)] underline">Ignore</button> : null}
      </div>
      {open ? (
        <div className="ml-[4.25rem] mt-2 space-y-3">
          {c.items.length > 0 ? (
            <ul className="max-h-80 space-y-1.5 overflow-y-auto rounded-lg bg-[var(--bg)] p-3 text-xs">
              {c.items.map((i) => (
                <li key={i.label} className="flex flex-wrap items-start gap-x-3 gap-y-0.5">
                  <span className={`min-w-0 break-all font-semibold ${i.kind === "missing" ? "text-red-700" : i.kind === "other" ? "text-[var(--text-secondary)]" : ""}`}>{i.label}</span>
                  {i.count > 1 ? <span className="text-[var(--text-tertiary)]">on {i.count} blocks</span> : null}
                  <span className="flex flex-wrap gap-2">
                    {i.pages.map((u) => <button key={u} type="button" onClick={() => onOpen(u)} className="break-all underline">{shortPage(u)}</button>)}
                    {i.count > i.pages.length && i.pages.length > 0 ? <span className="text-[var(--text-tertiary)]">and more</span> : null}
                  </span>
                </li>
              ))}
            </ul>
          ) : !extra ? (
            <p className="rounded-lg bg-[var(--bg)] p-3 text-xs text-[var(--text-secondary)]">Nothing was found on any crawled page.</p>
          ) : null}
          {extra}
        </div>
      ) : null}
    </li>
  );
}

/** Find the brand's item on Wikidata and approve it, so generated markup can link to it. Only approved items are ever linked. */
function Concepts({ client, data, flush = false }: { client: Client; data: ScData; flush?: boolean }) {
  const router = useRouter();
  // Start with the first core topic that has no Wikidata item yet; the brand's own item is optional.
  const firstOpen = data.entity.checks.find((c) => c.key === "topics")?.items.find((i) => i.kind === "missing")?.label.split(":")[0];
  const [name, setName] = useState(firstOpen || data.entity.brand);
  const [found, setFound] = useState<Record<string, ScCandidate[]> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const search = () =>
    start(async () => {
      setError(null);
      const r = await searchConceptsAction(client.id, [name]);
      if (r.ok) setFound(r.value);
      else setError(r.error);
    });
  const approve = (c: ScCandidate) =>
    start(async () => {
      const r = await approveConceptAction(client.id, client.slug, { name: name.trim(), qid: c.qid, label: c.label, description: c.description });
      if (r.ok) {
        setFound(null);
        router.refresh();
      } else setError(r.error);
    });
  const remove = (c: ScConcept) =>
    start(async () => {
      const r = await removeConceptAction(client.id, client.slug, c.id);
      if (r.ok) router.refresh();
      else setError(r.error);
    });
  const options = found ? Object.values(found)[0] ?? [] : [];
  return (
    <div className={`space-y-3 text-sm ${flush ? "" : "px-5 pb-5"}`}>
      <p className="text-xs text-[var(--text-tertiary)]">
        A Wikidata item is how search engines and AI recognize something as one known entity. Search for the brand or a topic, approve the item that is right, and generated markup will link to it. The model never chooses these.
      </p>
      {data.concepts.length > 0 ? (
        <ul className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
          {data.concepts.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center gap-3 px-3 py-2">
              <span className="font-semibold">{c.name}</span>
              <a href={c.url} target="_blank" rel="noreferrer" className="text-xs underline">{c.qid}</a>
              <span className="min-w-0 flex-1 text-xs text-[var(--text-secondary)]">{c.label}{c.description ? `: ${c.description}` : ""}</span>
              <button type="button" onClick={() => remove(c)} disabled={pending} className="text-xs font-semibold text-red-700 underline">Remove</button>
            </li>
          ))}
        </ul>
      ) : null}
      <div className="flex flex-wrap items-end gap-2">
        <label className="min-w-[14rem] flex-1 text-xs font-semibold">
          Concept to look up, or a Wikidata ID (Q…)
          <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block w-full rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-normal" />
        </label>
        <button type="button" onClick={search} disabled={pending || name.trim().length < 2} className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold disabled:opacity-50">
          {pending ? <><Spinner />Searching…</> : "Search Wikidata"}
        </button>
      </div>
      {error ? <p role="alert" className="font-semibold text-red-700">{error}</p> : null}
      {found ? (
        options.length === 0 ? (
          <p className="text-[var(--text-secondary)]">Wikidata has no item for “{name}”. If the brand is notable enough, creating one is the first step; until then the markup links to the brand&apos;s own profiles instead.</p>
        ) : (
          <div className="space-y-2">
            {options.map((c) => <CandidateCard key={c.qid} c={c} pending={pending} onApprove={approve} />)}
          </div>
        )
      ) : null}
    </div>
  );
}

const VERDICT: Record<string, { text: string; cls: string }> = {
  strong: { text: "Strong match", cls: "bg-green-100 text-green-800" },
  possible: { text: "Possible match", cls: "bg-amber-100 text-amber-800" },
  weak: { text: "Weak match", cls: "bg-amber-100 text-amber-800" },
  unlikely: { text: "Not this one", cls: "bg-red-100 text-red-800" },
};
const STATUS: Record<string, { text: string; cls: string }> = {
  match: { text: "Match", cls: "text-green-700" },
  conflict: { text: "Conflict", cls: "text-red-700" },
  missing: { text: "Not on the site", cls: "text-red-700" },
  none: { text: "No evidence", cls: "text-[var(--text-tertiary)]" },
  info: { text: "", cls: "" },
};

/** One Wikidata candidate. Closed until opened: the header says how well it fits, the body sets what Wikidata says beside what the site says. */
function CandidateCard({ c, pending, onApprove }: { c: ScCandidate; pending: boolean; onApprove: (c: ScCandidate) => void }) {
  const ev = c.evidence;
  const v = ev ? VERDICT[ev.verdict] : null;
  return (
    <details className="group rounded-lg border border-[var(--border)] bg-white">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-3 px-3 py-2">
        <span className="text-xs text-[var(--text-tertiary)] group-open:rotate-90" aria-hidden>▸</span>
        <span className="min-w-0 flex-1 text-xs"><strong>{c.label}</strong> <span className="text-[var(--text-tertiary)]">{c.qid}</span>{c.description ? <span className="block text-[var(--text-secondary)]">{c.description}</span> : null}</span>
        {v && ev ? <span className={`rounded-md px-2 py-0.5 text-xs font-semibold ${v.cls}`}>{v.text}{ev.matched + ev.conflicts > 0 ? ` · ${ev.matched} of ${ev.checked}` : " · nothing on the site to compare"}</span> : <span className="text-xs text-[var(--text-tertiary)]">No evidence fetched</span>}
      </summary>
      <div className="border-t border-[var(--border)] px-3 py-2 text-xs">
        {ev ? (
          <table className="w-full table-fixed border-collapse">
            <thead><tr className="text-left text-[var(--text-tertiary)]"><th className="w-[24%] py-1 font-normal" /><th className="w-[32%] py-1 font-normal">Wikidata says</th><th className="w-[30%] py-1 font-normal">The site says</th><th className="w-[14%] py-1 font-normal" /></tr></thead>
            <tbody>
              {ev.rows.map((r) => (
                <tr key={r.key} className="border-t border-[var(--border)] align-top">
                  <th className="py-1.5 pr-2 text-left font-semibold">{r.label}</th>
                  <td className="py-1.5 pr-2 break-words">{r.wikidata}</td>
                  <td className="py-1.5 pr-2 break-words">{r.site}</td>
                  <td className={`py-1.5 font-semibold ${STATUS[r.status]?.cls ?? ""}`}>{STATUS[r.status]?.text}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="text-[var(--text-secondary)]">Wikidata could not be read for this item just now, so there is only its name and description to go on.</p>}
        {ev && ev.profiles.length > 0 ? <p className="mt-2 text-[var(--text-secondary)]">Profiles listed on the item: {ev.profiles.join(", ")}</p> : null}
        <div className="mt-3 flex items-center gap-3">
          <button type="button" onClick={() => onApprove(c)} disabled={pending} className={`rounded-lg px-3 py-1 text-xs font-semibold disabled:opacity-50 ${ev?.verdict === "unlikely" || ev?.verdict === "weak" ? "border border-[var(--border)] bg-white" : "bg-[var(--brand-dark)] text-white"}`}>
            {ev?.verdict === "unlikely" || ev?.verdict === "weak" ? "Approve anyway" : "Approve this one"}
          </button>
          <a href={c.url} target="_blank" rel="noreferrer" className="underline">Open on Wikidata</a>
        </div>
      </div>
    </details>
  );
}

function Report({ r }: { r: ScReport }) {
  if (r.status === "running") return <p className="text-sm text-[var(--text-secondary)]"><Spinner />Working on it…</p>;
  if (r.status === "failed") return <p role="alert" className="text-sm font-semibold text-red-700">{r.error ?? "That did not work."}</p>;
  return null;
}

/** One page: what the crawl holds, and the two things the model can do for it. */
function PagePane({ client, url, ready, depths, onClose, onApproved }: { client: Client; url: string; ready: boolean; depths: Record<string, string>; onClose: () => void; onApproved: () => void }) {
  const [page, setPage] = useState<ScPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<ScDepth>("quick");
  const [copied, setCopied] = useState(false);
  const [pending, start] = useTransition();
  const load = () => pageAction(client.id, url).then((r) => (r.ok ? setPage(r.value) : setError(r.error)));
  useEffect(() => {
    setPage(null);
    setError(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url]);
  const running = page && (page.reports.audit?.status === "running" || page.reports.markup?.status === "running");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const run = (kind: "audit" | "markup") =>
    start(async () => {
      setError(null);
      const r = await startPageReportAction(client.id, kind, url, depth);
      if (!r.ok) setError(r.error);
      else await load();
    });
  const approve = (name: string, c: ScCandidate) =>
    start(async () => {
      const r = await approveConceptAction(client.id, client.slug, { name, qid: c.qid, label: c.label, description: c.description });
      if (r.ok) {
        onApproved();
        await load();
      } else setError(r.error);
    });
  const audit = page?.reports.audit;
  const markup = page?.reports.markup;
  return (
    <div className="space-y-4 text-sm">
      <p className="break-all font-semibold">{url}</p>
      {error ? <p role="alert" className="font-semibold text-red-700">{error}</p> : null}
      {!page && !error ? <p className="text-[var(--text-secondary)]"><Spinner />Reading the page…</p> : null}
      {page ? (
        <>
          <div className="rounded-lg bg-[var(--bg)] p-3 text-xs">
            <div><strong>Kind of page:</strong> {page.page_type.replace(/_/g, " ")} · <strong>Score:</strong> {Math.round(page.score * 100)}</div>
            <div className="mt-1"><strong>Markup it has:</strong> {page.present.length ? page.present.join(", ") : "none"}</div>
            {page.missing_required.length > 0 ? <div className="mt-1 text-red-700"><strong>Missing:</strong> {page.missing_required.join(", ")}</div> : <div className="mt-1 text-green-700"><strong>Clean:</strong> nothing required is missing</div>}
            {page.missing_recommended.length > 0 ? <div className="mt-1 text-[var(--text-secondary)]"><strong>Worth adding:</strong> {page.missing_recommended.join(", ")}</div> : null}
          </div>
          {page.findings && page.findings.length > 0 ? (
            <ul className="space-y-2 text-xs">
              {page.findings.map((f, i) => (
                <li key={i} className="rounded-lg border border-[var(--border)] p-2">
                  <Badges f={f} />
                  <div className="mt-1 font-semibold">{f.title}</div>
                  <div className="text-[var(--text-secondary)]">{f.message}</div>
                  <details className="mt-1"><summary className="cursor-pointer font-semibold">Why, and what to do</summary>
                    <p className="mt-1">{f.explanation}</p><p className="mt-1"><strong>What to do:</strong> {f.recommendation}</p>
                    <Evidence value={f.evidence} />
                    <a href={f.doc} target="_blank" rel="noreferrer" className="mt-1 inline-block font-semibold text-[var(--brand-teal)] underline">Documentation</a> <span className="text-[var(--text-tertiary)]">Rule {f.rule_id}{f.entity_id ? ` · ${f.entity_id}` : ""}</span>
                  </details>
                </li>
              ))}
            </ul>
          ) : null}
          {page.existing.length > 0 ? (
            <details className="text-xs"><summary className="cursor-pointer font-semibold">The markup on the page now</summary><pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-[var(--bg)] p-3">{page.existing.join("\n\n")}</pre></details>
          ) : null}

          {ready ? (
            <div className="flex flex-wrap items-end gap-2 border-t border-[var(--border)] pt-3">
              <label className="text-xs font-semibold">
                How deep
                <select value={depth} onChange={(e) => setDepth(e.target.value as ScDepth)} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-2 text-sm font-normal">
                  {(Object.keys(DEPTH) as ScDepth[]).map((d) => <option key={d} value={d}>{DEPTH[d]}</option>)}
                </select>
              </label>
              <button type="button" onClick={() => run("audit")} disabled={pending || !!running} className="rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm font-semibold disabled:opacity-50">Audit this page</button>
              <button type="button" onClick={() => run("markup")} disabled={pending || !!running} className="rounded-lg bg-[var(--brand-dark)] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">Write corrected markup</button>
            </div>
          ) : <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-900">The model tools need the Anthropic key on the API service.</p>}

          {audit ? (
            <section className="space-y-2 border-t border-[var(--border)] pt-3">
              <h3 className="font-bold">Audit <span className="text-xs font-normal text-[var(--text-tertiary)]">{DEPTH[audit.depth]} · ${audit.cost_usd.toFixed(2)}</span></h3>
              <Report r={audit} />
              {audit.status === "done" ? (
                <>
                  <p><strong>{audit.intent}:</strong> {audit.intent_explanation}</p>
                  {audit.diagnosis && audit.diagnosis.length > 0 ? <div><h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">What is wrong</h4><ul className="mt-1 list-disc space-y-1 pl-5">{audit.diagnosis.map((d, i) => <li key={i}>{d}</li>)}</ul></div> : null}
                  {audit.fix_plan && audit.fix_plan.length > 0 ? <div><h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Fix plan</h4><ol className="mt-1 list-decimal space-y-1 pl-5">{audit.fix_plan.map((d, i) => <li key={i}>{d}</li>)}</ol></div> : null}
                  {audit.concepts && audit.concepts.length > 0 ? (
                    <div>
                      <h4 className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">Concepts to link to Wikidata</h4>
                      <ul className="mt-1 space-y-2">
                        {audit.concepts.map((c) => (
                          <li key={c.name} className="rounded-lg border border-[var(--border)] p-2">
                            <div className="font-semibold">{c.name}{c.approved_qid ? <span className="ml-2 text-xs font-normal text-green-700">approved: {c.approved_qid}</span> : null}</div>
                            {c.candidates.length === 0 ? <div className="text-xs text-[var(--text-secondary)]">No Wikidata item found.</div> : (
                              <ul className="mt-1 space-y-1">
                                {c.candidates.map((x) => (
                                  <li key={x.qid} className="flex flex-wrap items-center gap-2 text-xs">
                                    <a href={x.url} target="_blank" rel="noreferrer" className="font-semibold underline">{x.qid}</a>
                                    <span className="min-w-0 flex-1">{x.label}{x.description ? `: ${x.description}` : ""}</span>
                                    {c.approved_qid === x.qid ? <span className="font-semibold text-green-700">Approved</span> : <button type="button" onClick={() => approve(c.name, x)} disabled={pending} className="font-semibold underline">Approve</button>}
                                  </li>
                                ))}
                              </ul>
                            )}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </>
              ) : null}
            </section>
          ) : null}

          {markup ? (
            <section className="space-y-2 border-t border-[var(--border)] pt-3">
              <h3 className="font-bold">Corrected markup <span className="text-xs font-normal text-[var(--text-tertiary)]">{DEPTH[markup.depth]} · ${markup.cost_usd.toFixed(2)}</span></h3>
              <Report r={markup} />
              {markup.status === "done" && markup.json_ld ? (
                <>
                  <p className="text-xs text-[var(--text-secondary)]">
                    A draft for a person to check before it goes live, for example in Google&apos;s Rich Results Test. {markup.approved && markup.approved.length > 0 ? `It links only to the approved items: ${markup.approved.map((a) => a.name).join(", ")}.` : "No Wikidata items are approved yet, so it links to none."}
                  </p>
                  <pre className="max-h-96 overflow-auto rounded-lg bg-[var(--bg)] p-3 text-xs">{markup.json_ld}</pre>
                  <button type="button" onClick={() => { void navigator.clipboard.writeText(markup.json_ld ?? "").then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }); }} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold">{copied ? "Copied" : "Copy"}</button>
                  {markup.post_corrections && markup.post_corrections.length > 0 ? <details className="text-xs"><summary className="cursor-pointer font-semibold">Cleaned up after it was written ({markup.post_corrections.length})</summary><ul className="mt-1 list-disc pl-5 text-[var(--text-secondary)]">{markup.post_corrections.map((c, i) => <li key={i}>{c}</li>)}</ul></details> : null}
                </>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}

export function SchemaScreen({ client, result, error }: { client: Client; result: ScResponse | null; error: string | null }) {
  const router = useRouter();
  const data = result?.data ?? null;
  const [open, setOpen] = useState<string | null>(useSearchParams().get("page"));
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const [openChecks, setOpenChecks] = useState<Set<string>>(new Set());
  const toggleCheck = (key: string) =>
    setOpenChecks((prev) => {
      const next = new Set(prev);
      if (!next.delete(key)) next.add(key);
      return next;
    });
  const [ignoreError, setIgnoreError] = useState<string | null>(null);
  const [, startIgnore] = useTransition();
  const ignore: Ignore = (scope, key, label) =>
    startIgnore(async () => {
      setIgnoreError(null);
      const r = await addIgnoreAction(client.id, client.slug, scope, key, label);
      if (r.ok) router.refresh();
      else setIgnoreError(r.error);
    });
  const restore = (id: string) =>
    startIgnore(async () => {
      setIgnoreError(null);
      const r = await removeIgnoreAction(client.id, client.slug, id);
      if (r.ok) router.refresh();
      else setIgnoreError(r.error);
    });
  const counted = data ? data.entity.checks.filter((c) => c.status !== "ignored" && c.status !== "optional") : [];
  const passing = counted.filter((c) => c.status === "pass").length;
  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Machine readability</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          What structured data each kind of page carries against what it should, and whether the brand reads as one known entity. Built on the Topic Hub schema audit.
        </p>
      </header>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {!error && !data ? <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This site has not been crawled yet, so there is nothing to audit. Pull data on the Connections page starts a crawl.</p> : null}
      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Markup score" value={String(data.score)} note="average of every page, out of 100" />
            <Kpi label="Pages with markup" value={`${data.with_markup} of ${data.pages}`} note="indexable pages with a JSON-LD block" />
            <Kpi label="Errors and warnings" value={String(data.cleanups)} note="found across all pages" />
            <Kpi label="Brand entity checks" value={`${passing} of ${counted.length}`} note="clean" />
          </div>

          <Findings data={data} onOpen={setOpen} onIgnore={ignore} />

          <section className={card}>
            <h2 className="px-5 pt-4 text-lg font-bold">By kind of page</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">Each page starts at 100 and loses points for markup it is missing. A kind's score is the average of its pages. Green is 85 or more, amber 70 to 84, red under 70. Open any page to audit it or write corrected markup. From the crawl of {day(data.crawl_date)}.</p>
            <ul className="divide-y divide-[var(--border)] px-5 pb-2">{data.types.map((t) => <TypeRow key={t.page_type} t={t} onOpen={setOpen} onIgnore={ignore} />)}</ul>
          </section>

          <section className={card}>
            <h2 className="px-5 pt-4 text-lg font-bold">Core topics and the brand</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">Most brands have no Wikidata item of their own, so the markup links {data.entity.brand || "the brand"}&apos;s core topics to Wikidata items instead. Those are what search engines and AI recognize. The brand&apos;s own checks follow.</p>
            <div className="flex justify-end gap-3 px-5 text-xs">
              <button type="button" onClick={() => setOpenChecks(new Set(data.entity.checks.map((c) => c.key)))} className="underline">Expand all</button>
              <button type="button" onClick={() => setOpenChecks(new Set())} className="underline">Collapse all</button>
            </div>
            <ul className="divide-y divide-[var(--border)] px-5 pb-2">
              {data.entity.checks.map((c) => (
                <CheckRow key={c.key} c={c} open={openChecks.has(c.key)} onToggle={() => toggleCheck(c.key)} onIgnore={ignore} onOpen={setOpen} extra={c.key === "topics" ? <Concepts client={client} data={data} flush /> : undefined} />
              ))}
            </ul>
          </section>

          {ignoreError ? <p role="alert" className="text-sm font-semibold text-red-700">{ignoreError}</p> : null}
          {data.ignored.length > 0 ? (
            <section className={`${card} p-5`}>
              <h2 className="text-lg font-bold">Ignored for this client</h2>
              <p className="text-xs text-[var(--text-tertiary)]">These are not counted. Restore any of them and they count again.</p>
              <ul className="mt-2 divide-y divide-[var(--border)] text-sm">
                {data.ignored.map((i) => (
                  <li key={i.id} className="flex items-center gap-3 py-2">
                    <span className="min-w-0 flex-1 break-all">{i.label}</span>
                    <button type="button" onClick={() => restore(i.id)} className="text-xs font-semibold underline">Restore</button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {data.invalid.length > 0 ? (
            <section className={`${card} p-5`}>
              <h2 className="text-lg font-bold">Markup that does not parse</h2>
              <ul className="mt-2 space-y-1 text-xs">
                {data.invalid.map((i) => <li key={i.url}><button type="button" onClick={() => setOpen(i.url)} className="font-semibold underline">{shortPage(i.url)}</button> <span className="text-[var(--text-secondary)]">{i.error}</span></li>)}
              </ul>
            </section>
          ) : null}
        </>
      ) : null}

      <aside aria-label="Page" aria-hidden={!open} className={`fixed right-0 top-0 z-30 flex h-full w-full max-w-2xl flex-col border-l border-[var(--border)] bg-[var(--surface)] shadow-xl transition-transform duration-200 ${open ? "translate-x-0" : "pointer-events-none translate-x-full"}`}>
        <div className="flex items-center justify-between border-b border-[var(--border)] px-5 py-3">
          <h2 className="font-bold">Page</h2>
          <button type="button" onClick={() => setOpen(null)} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-sm font-semibold">Close</button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {open ? <PagePane client={client} url={open} ready={result?.ready ?? false} depths={result?.depths ?? {}} onClose={() => setOpen(null)} onApproved={() => router.refresh()} /> : null}
        </div>
      </aside>
    </section>
  );
}
