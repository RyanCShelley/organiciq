"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";

import { ignoreInlinkAction, restoreInlinkAction, verifyInlinkAction } from "@/app/(app)/[clientSlug]/inlinks/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { InData, InSuggestion, InTarget } from "@/lib/inlinks";

const card = "rounded-xl border border-[var(--border)] bg-[var(--surface)]";
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const TYPE: Record<string, string> = { partial_match: "describes the page", branded: "brand", generic: "generic", naked_url: "address" };

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className={`${card} p-4`}>
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-3xl font-bold tabular-nums">{value}</div>
      {note ? <div className="mt-1 text-xs text-[var(--text-secondary)]">{note}</div> : null}
    </div>
  );
}

function Suggestion({ client, target, s, onChanged }: { client: Client; target: string; s: InSuggestion; onChanged: () => void }) {
  const [anchor, setAnchor] = useState(s.suggested_anchor);
  const [copied, setCopied] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [pending, start] = useTransition();
  const check = () =>
    start(async () => {
      setMessage(null);
      const r = await verifyInlinkAction(client.id, s.source_url, target);
      if (!r.ok) setMessage({ ok: false, text: r.error });
      else if (!r.value.checked) setMessage({ ok: false, text: r.value.error ?? "The page could not be checked." });
      else if (r.value.found) {
        setMessage({ ok: true, text: `Live${r.value.anchor ? ` with the anchor “${r.value.anchor}”` : ""}. It will not be suggested again.` });
        onChanged();
      } else setMessage({ ok: false, text: "Not on the page yet. If it was just published, the page may still be cached." });
    });
  const ignore = () =>
    start(async () => {
      const r = await ignoreInlinkAction(client.id, client.slug, target, s.source_url);
      if (r.ok) onChanged();
      else setMessage({ ok: false, text: r.error });
    });
  return (
    <li className="space-y-1 rounded-lg border border-[var(--border)] bg-white p-3">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-xs text-[var(--text-tertiary)]">Add a link on</div>
          <a href={s.source_url} target="_blank" rel="noreferrer" className="break-all font-semibold underline">{shortPage(s.source_url)}</a>
          <div className="truncate text-xs text-[var(--text-secondary)]" title={s.source_title}>{s.source_title}</div>
        </div>
        <div className="flex gap-3 text-xs">
          <button type="button" onClick={check} disabled={pending} className="font-semibold underline">{pending ? <><Spinner />Checking…</> : "Check it's live"}</button>
          <button type="button" onClick={ignore} disabled={pending} className="text-[var(--text-tertiary)] underline">Ignore</button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs font-semibold">Anchor text</span>
        <input value={anchor} onChange={(e) => setAnchor(e.target.value)} aria-label="Anchor text" className="min-w-[14rem] flex-1 rounded-lg border border-[var(--border)] bg-white px-2 py-1 text-sm" />
        <button type="button" onClick={() => void navigator.clipboard.writeText(anchor).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })} className="rounded-lg border border-[var(--border)] bg-white px-2 py-1 text-xs font-semibold">{copied ? "Copied" : "Copy"}</button>
      </div>
      {s.anchor_alternates.length > 0 ? (
        <div className="flex flex-wrap gap-1.5 text-xs text-[var(--text-secondary)]">
          <span>Or:</span>
          {s.anchor_alternates.map((a) => (
            <button key={a.anchor} type="button" onClick={() => setAnchor(a.anchor)} className="rounded bg-[var(--bg)] px-1.5 py-0.5 hover:underline" title={TYPE[a.type] ?? a.type}>{a.anchor}</button>
          ))}
        </div>
      ) : null}
      <ul className="list-disc pl-5 text-xs text-[var(--text-secondary)]">{s.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
      {message ? <p role={message.ok ? undefined : "alert"} className={`text-xs font-semibold ${message.ok ? "text-green-700" : "text-red-700"}`}>{message.text}</p> : null}
    </li>
  );
}

/** The same page however its address is written: with or without www, a trailing slash, a query. */
function sameAddress(a: string, b: string): boolean {
  const clean = (u: string) => u.trim().toLowerCase().replace(/^https?:\/\/(www\.)?/, "").replace(/[?#].*$/, "").replace(/\/+$/, "");
  return clean(a) === clean(b);
}

function TargetRow({ client, t, onChanged }: { client: Client; t: InTarget; onChanged: () => void }) {
  const wanted = useSearchParams().get("target");
  const [open, setOpen] = useState(!!wanted && sameAddress(wanted, t.target_url));
  const [pending, start] = useTransition();
  const ignorePage = () =>
    start(async () => {
      const r = await ignoreInlinkAction(client.id, client.slug, t.target_url, null);
      if (r.ok) onChanged();
    });
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-0 flex-1">
          <div className="break-all font-semibold">{shortPage(t.target_url)}</div>
          <div className="truncate text-xs text-[var(--text-tertiary)]" title={t.title}>{t.title}</div>
          <div className="text-xs text-[var(--text-secondary)]">
            {t.inbound === 0 ? <span className="font-semibold text-red-700">No editorial links</span> : t.inbound >= t.wanted ? <span className="font-semibold text-green-700">Clean: {t.inbound} editorial links</span> : <span>{t.inbound} of {t.wanted} editorial links</span>}
            {t.impressions > 0 ? ` · ${num(t.impressions)} impressions${t.position != null ? `, best position ${t.position}` : ""}` : ""}
            {t.queries.length > 0 ? ` · ranks for “${t.queries[0]}”` : ""}
          </div>
        </div>
        <button type="button" onClick={() => setOpen((v) => !v)} className="text-xs font-semibold underline">{open ? "Hide" : t.inbound >= t.wanted ? `Show ${t.suggestions.length} more possible` : `Show ${t.suggestions.length} to fix`}</button>
        <button type="button" onClick={ignorePage} disabled={pending} className="text-xs text-[var(--text-tertiary)] underline">Ignore this page</button>
      </div>
      {open ? <ul className="mt-2 space-y-2">{t.suggestions.map((s) => <Suggestion key={s.source_url} client={client} target={t.target_url} s={s} onChanged={onChanged} />)}</ul> : null}
    </li>
  );
}

export function InlinkSuggester({ client, q, data, error }: { client: Client; q: string; data: InData | null; error: string | null }) {
  const router = useRouter();
  const [, start] = useTransition();
  const refresh = () => router.refresh();
  const [search, setSearch] = useState(q);
  const find = (query: string) => router.push(`/${client.slug}/inlinks${query ? `?${new URLSearchParams({ q: query })}` : ""}`);
  const restore = (id: string) =>
    start(async () => {
      const r = await restoreInlinkAction(client.id, client.slug, id);
      if (r.ok) router.refresh();
    });
  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Inlink suggester</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Which page should link to which. It joins the site crawl (what links where now), Search Console (what each page earns) and how alike two pages are in subject, with anchor text from the Topic Hub tool.
        </p>
      </header>
      <form className="flex flex-wrap items-center gap-2 text-sm" role="search" onSubmit={(e) => { e.preventDefault(); find(search.trim()); }}>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Find a page: part of its address, its title, or a search it ranks for"
          aria-label="Find a page"
          className="min-w-[20rem] flex-1 rounded-lg border border-[var(--border)] bg-white px-3 py-2"
        />
        <button type="submit" className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 font-semibold">Find</button>
        {q ? <button type="button" onClick={() => { setSearch(""); find(""); }} className="text-xs font-semibold underline">Clear</button> : null}
      </form>
      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {!error && !data ? <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This site has not been crawled yet, or has too few pages, so there is nothing to suggest. Pull data on the Connections page starts a crawl.</p> : null}
      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Pages to link to" value={num(data.summary.targets)} note={`of ${num(data.pages)} crawled pages`} />
            <Kpi label="Links to add" value={num(data.summary.suggestions)} note="from pages that are alike and do not link yet" />
            <Kpi label="No editorial links" value={num(data.summary.orphans)} note="pages nothing links to in its own content" />
            <Kpi label="Confirmed live" value={num(data.summary.live)} note="links checked on the page" />
          </div>

          <section className={card}>
            <h2 className="px-5 pt-4 text-lg font-bold">{q ? `Pages matching “${q}”` : "Pages that need links, most worth it first"}</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">{data.rule} Worked out from the crawl of {day(data.crawl_date)}. Add the link, then use Check it&apos;s live to confirm it.</p>
            {data.targets.length === 0 ? (
              <p className={`px-5 py-4 text-sm font-semibold ${q ? "text-[var(--text-secondary)]" : "text-green-700"}`}>{q ? `No crawled page matches “${q}”, or nothing alike is left to link from it.` : "Clean: every page that earns search traffic has enough links, or nothing alike is left to link from."}</p>
            ) : (
              <ul className="divide-y divide-[var(--border)] px-5 pb-2">{data.targets.map((t) => <TargetRow key={t.target_url} client={client} t={t} onChanged={refresh} />)}</ul>
            )}
          </section>

          {data.ignored.length > 0 ? (
            <section className={`${card} p-5`}>
              <h2 className="text-lg font-bold">Ignored for this client</h2>
              <ul className="mt-2 divide-y divide-[var(--border)] text-sm">
                {data.ignored.map((i) => (
                  <li key={i.id} className="flex items-center gap-3 py-2">
                    <span className="min-w-0 flex-1 break-all">{i.source ? `${shortPage(i.source)} → ${shortPage(i.target)}` : `Every link to ${shortPage(i.target)}`}</span>
                    <button type="button" onClick={() => restore(i.id)} className="text-xs font-semibold underline">Restore</button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
