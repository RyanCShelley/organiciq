"use client";

import { useRouter } from "next/navigation";
import { Fragment, useEffect, useState, useTransition } from "react";

import { addIgnoreAction, approveConceptAction, pageAction, removeConceptAction, removeIgnoreAction, searchConceptsAction, startPageReportAction } from "@/app/(app)/[clientSlug]/schema/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { ScCandidate, ScCheck, ScConcept, ScData, ScDepth, ScIgnoreScope, ScItem, ScPage, ScReport, ScResponse, ScType } from "@/lib/schema";

type Ignore = (scope: ScIgnoreScope, key: string, label: string) => void;

const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const tone = (score: number) => (score >= 85 ? "#0f766e" : score >= 70 ? "#b45309" : "#b91c1c");
const DEPTH: Record<ScDepth, string> = { quick: "Quick (Sonnet 5.5)", deep: "Deep dive (Opus 5.5)", deepest: "Deepest (Fable 5.1)" };

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

function TypeRow({ t, onOpen, onIgnore }: { t: ScType; onOpen: (url: string) => void; onIgnore: Ignore }) {
  const [open, setOpen] = useState<"fix" | "rec" | null>(null);
  const items: ScItem[] = open === "rec" ? t.recommended_items : t.items;
  const total = open === "rec" ? t.recommended_affected : t.affected;
  const clean = t.affected === 0;
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
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
        <div className="flex w-52 justify-end gap-3 text-xs">
          {clean ? <span className="font-semibold text-green-700">Clean</span> : <button type="button" onClick={() => setOpen(open === "fix" ? null : "fix")} className="font-semibold underline">{open === "fix" ? "Hide" : `Show ${t.affected} to fix`}</button>}
          {t.recommended_affected > 0 ? <button type="button" onClick={() => setOpen(open === "rec" ? null : "rec")} className="text-[var(--text-secondary)] underline">{open === "rec" ? "Hide" : `${t.recommended_affected} could add more`}</button> : null}
        </div>
      </div>
      {open ? (
        <ul className="mt-2 max-h-72 space-y-1.5 overflow-y-auto rounded-lg bg-[var(--bg)] p-3 text-xs">
          {items.map((i) => (
            <li key={i.url} className="flex flex-wrap items-start gap-2">
              <button type="button" onClick={() => onOpen(i.url)} className="break-all text-left font-semibold underline">{shortPage(i.url)}</button>
              <span className="min-w-0 flex-1 text-[var(--text-secondary)]">{i.text}</span>
              <button type="button" onClick={() => onIgnore("page", i.url, `${shortPage(i.url)}: ignored`)} className="text-[var(--text-tertiary)] underline">Ignore</button>
            </li>
          ))}
          {total > items.length ? <li className="text-[var(--text-tertiary)]">and {total - items.length} more</li> : null}
        </ul>
      ) : null}
    </li>
  );
}

function CheckRow({ c, onIgnore }: { c: ScCheck; onIgnore: Ignore }) {
  const clean = c.status === "pass";
  const ignored = c.status === "ignored";
  return (
    <li className="flex flex-wrap items-start gap-3 py-3">
      <span className={`mt-0.5 w-14 shrink-0 text-xs font-semibold ${clean ? "text-green-700" : ignored ? "text-[var(--text-tertiary)]" : c.status === "warn" ? "text-amber-700" : "text-red-700"}`}>{clean ? "Clean" : ignored ? "Ignored" : "To fix"}</span>
      <div className="min-w-0 flex-1">
        <div className={`font-semibold ${ignored ? "text-[var(--text-tertiary)]" : ""}`}>{c.label}</div>
        <div className="text-xs text-[var(--text-secondary)]">{c.detail}</div>
        {c.fix ? <div className="mt-0.5 text-xs font-medium">{c.fix}</div> : null}
      </div>
      {!clean && !ignored ? <button type="button" onClick={() => onIgnore("check", c.key, c.label)} className="text-xs text-[var(--text-tertiary)] underline">Ignore</button> : null}
    </li>
  );
}

/** Find the brand's item on Wikidata and approve it, so generated markup can link to it. Only approved items are ever linked. */
function Concepts({ client, data }: { client: Client; data: ScData }) {
  const router = useRouter();
  const [name, setName] = useState(data.entity.brand);
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
    <div className="space-y-3 px-5 pb-5 text-sm">
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
          Concept to look up
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
          <ul className="divide-y divide-[var(--border)] rounded-lg border border-[var(--border)]">
            {options.map((c) => (
              <li key={c.qid} className="flex flex-wrap items-center gap-3 px-3 py-2">
                <a href={c.url} target="_blank" rel="noreferrer" className="text-xs font-semibold underline">{c.qid}</a>
                <span className="min-w-0 flex-1 text-xs"><strong>{c.label}</strong>{c.description ? `: ${c.description}` : ""}</span>
                <button type="button" onClick={() => approve(c)} disabled={pending} className="rounded-lg bg-[var(--brand-dark)] px-3 py-1 text-xs font-semibold text-white disabled:opacity-50">Approve this one</button>
              </li>
            ))}
          </ul>
        )
      ) : null}
    </div>
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
            {page.corrections.length > 0 ? (
              <ul className="mt-1 list-disc pl-4 text-[var(--text-secondary)]">{page.corrections.map((c, i) => <li key={i}>{c.detail}</li>)}</ul>
            ) : null}
          </div>
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
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
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
  const counted = data ? data.entity.checks.filter((c) => c.status !== "ignored") : [];
  const passing = counted.filter((c) => c.status === "pass").length;
  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Schema &amp; knowledge graph</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          What structured data each kind of page carries against what it should, and whether the brand reads as one known entity. Built on the Topic Hub schema audit.
        </p>
      </header>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {!error && !data ? <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This site has not been crawled yet, so there is nothing to audit. Pull data on the Connections page starts a crawl.</p> : null}
      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Markup score" value={String(data.score)} note="how complete each page's markup is for its kind" />
            <Kpi label="Pages with markup" value={`${data.with_markup} of ${data.pages}`} note="indexable pages with a JSON-LD block" />
            <Kpi label="Cleanups found" value={String(data.cleanups)} note="invalid or misplaced properties in the markup now" />
            <Kpi label="Brand entity checks" value={`${passing} of ${counted.length}`} note="clean" />
          </div>

          <section className={card}>
            <h2 className="px-5 pt-4 text-lg font-bold">By kind of page</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">The score is how complete the markup is for that kind of page. Open any page to audit it or write corrected markup. Worked out from the crawl of {day(data.crawl_date)}.</p>
            <ul className="divide-y divide-[var(--border)] px-5 pb-2">{data.types.map((t) => <TypeRow key={t.page_type} t={t} onOpen={setOpen} onIgnore={ignore} />)}</ul>
          </section>

          {data.fixes.length > 0 ? (
            <section className={`${card} p-5`}>
              <h2 className="text-lg font-bold">Fix once, clear many pages</h2>
              <p className="text-xs text-[var(--text-tertiary)]">These repeat across pages, so they usually come from one template. Fixing the template clears them all.</p>
              <ul className="mt-3 space-y-2 text-sm">
                {data.fixes.map((f) => (
                  <li key={f.text} className="flex flex-wrap items-center gap-3">
                    <span className="w-24 shrink-0 font-bold tabular-nums">{f.pages} pages</span>
                    <span className="min-w-0 flex-1">{f.text}</span>
                    <button type="button" onClick={() => setOpen(f.example)} className="text-xs font-semibold underline">See an example</button>
                    <button type="button" onClick={() => ignore(f.ignore.scope, f.ignore.key, f.ignore.label)} className="text-xs text-[var(--text-tertiary)] underline">Ignore</button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className={card}>
            <h2 className="px-5 pt-4 text-lg font-bold">The brand as one entity</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">Does the markup describe {data.entity.brand || "the brand"} as one organization, tied to the profiles and the Wikidata item that identify it?</p>
            <ul className="divide-y divide-[var(--border)] px-5 pb-2">{data.entity.checks.map((c) => <CheckRow key={c.key} c={c} onIgnore={ignore} />)}</ul>
            <h3 className="px-5 pt-2 font-semibold">Wikidata items</h3>
            <Concepts client={client} data={data} />
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
