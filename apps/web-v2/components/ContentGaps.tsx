"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useTransition } from "react";

import { briefAction, dismissTopicAction, draftAction, setAsideAction, topicDetailAction, topicsAction } from "@/app/(app)/[clientSlug]/content-gaps/actions";
import { AddToCalendar, StatusChip } from "@/components/content/AddToCalendar";
import { AskModel, DEPTH, Kpi, List, SidePane, card, num, shortPage, td, th } from "@/components/content/parts";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import type { Brief, CalendarStatus, ContentDepthChoice, Gap, GapSource, Gaps, TopicDetail, TopicsResponse } from "@/lib/content";

const SOURCE: Record<GapSource, string> = { searched: "Shown in Google", competitor: "Competitors rank", watchlist: "On the watchlist" };

function BriefPane({ client, gap, ready, canEdit, onCalendar, onRefresh, onChanged }: { client: Client; gap: Gap; ready: boolean; canEdit: boolean; onCalendar?: CalendarStatus; onRefresh: () => void; onChanged: () => void }) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<ContentDepthChoice>("quick");
  const [pending, start] = useTransition();
  const now = useRef(`${client.id}|${gap.term}`);
  now.current = `${client.id}|${gap.term}`;
  const load = () => {
    const asked = now.current;
    return briefAction(client.id, gap.term).then((r) => {
      if (now.current !== asked) return; // a reply for a gap no longer open
      if (r.ok) setBrief(r.value);
      else setError(r.error);
    });
  };
  useEffect(() => {
    setBrief(null);
    setError(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client.id, gap.term]);
  const running = brief?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const write = () =>
    start(async () => {
      setError(null);
      const r = await draftAction(client.id, "brief", gap.term, depth);
      if (!r.ok) setError(r.error);
      else await load();
    });
  const setAside = () =>
    start(async () => {
      const r = await setAsideAction(client.id, "gap", gap.term, gap.ignored);
      if (!r.ok) setError(r.error);
      else onChanged();
    });

  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-lg font-bold">{gap.term}</p>
          <p className="text-xs text-[var(--text-secondary)]">{gap.sources.map((s) => SOURCE[s]).join(" · ")}{gap.intents.length ? ` · ${gap.intents.join(", ")}` : ""}</p>
        </div>
        <button type="button" onClick={setAside} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold disabled:opacity-50">{gap.ignored ? "Restore" : "Ignore"}</button>
      </div>
      {error ? <p role="alert" className="font-semibold text-red-700">{error}</p> : null}

      <div className="rounded-lg bg-[var(--bg)] p-3 text-xs">
        <div className="font-semibold">{gap.action}</div>
        <p className="mt-1">{gap.why}</p>
        <p className="mt-1 text-[var(--text-secondary)]">
          {gap.volume != null ? `${num(gap.volume)} searches a month${gap.difficulty != null ? `, difficulty ${Math.round(gap.difficulty)}` : ""}. ` : ""}
          {gap.impressions ? `Shown ${num(gap.impressions)} times in 90 days${gap.position != null ? ` at position ${gap.position}` : ""}, ${num(gap.clicks)} clicks. ` : ""}
          {gap.opportunity ? `About ${num(gap.opportunity)} searches a month to compete for.` : ""}
        </p>
        {gap.also_covers.length ? <p className="mt-1 text-[var(--text-secondary)]">One page can also answer: {gap.also_covers.join(", ")}.</p> : null}
      </div>

      {gap.competitors.length ? (
        <div>
          <h3 className="font-bold">Who ranks for it</h3>
          <ul className="mt-1 text-xs">{gap.competitors.map((c) => <li key={c.domain}>{c.domain} · position {c.position}</li>)}</ul>
        </div>
      ) : null}

      <div>
        <h3 className="font-bold">Closest pages on the site</h3>
        {gap.nearest.length === 0 ? <p className="text-xs text-[var(--text-secondary)]">No page shares its words.</p> : (
          <ul className="mt-1 space-y-1 text-xs">
            {gap.nearest.map((n) => (
              <li key={n.url} className="rounded-lg border border-[var(--border)] p-2">
                <div className="break-all font-semibold">{shortPage(n.url)}</div>
                <div className="text-[var(--text-secondary)]">{n.title ?? "no title found"}{n.shared.length ? ` · shares: ${n.shared.join(", ")}` : ""}</div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <AddToCalendar client={client} canEdit={canEdit} status={onCalendar} kind="new_page" title={brief?.status === "done" && brief.working_title ? brief.working_title : gap.term} target={gap.term} sourceArea="gap" sourceKey={gap.term} onAdded={onRefresh} />

      <div className="space-y-2 rounded-lg border border-[var(--border)] p-3">
        <h3 className="font-bold">Content brief</h3>
        <p className="text-xs text-[var(--text-tertiary)]">The model reads what is above and drafts a brief a writer can start from. A draft: nothing is sent anywhere and it uses no page allowance.</p>
        <AskModel ready={ready} depth={depth} onDepth={setDepth} busy={pending || running} again={brief?.status === "done"} label="Write a brief" onRun={write} />
        {brief?.status === "failed" ? <p role="alert" className="text-xs font-semibold text-red-700">{brief.error}</p> : null}
        {brief?.status === "done" ? (
          <BriefBody brief={brief} heading={gap.term} />
        ) : null}
      </div>
    </div>
  );
}

function BriefBody({ brief, heading }: { brief: Brief; heading: string }) {
  const [copied, setCopied] = useState(false);
  const asText = (b: Brief) =>
    [`Brief: ${heading}`, `Title: ${b.working_title}`, `Type: ${b.page_type}`, `Angle: ${b.angle}`, `Target length: ${b.target_words ?? "?"} words`, "", "Sections:", ...(b.sections ?? []).map((s) => `- ${s}`), "", "Questions to answer:", ...(b.questions ?? []).map((s) => `- ${s}`), "", "Cover:", ...(b.entities ?? []).map((s) => `- ${s}`), "", "Link from:", ...(b.link_from ?? []).map((l) => `- ${l.url} (${l.anchor_idea})`)].join("\n");
  return (
    <div className="space-y-3 pt-1">
      <div>
        <div className="text-base font-bold">{brief.working_title}</div>
        <div className="text-xs text-[var(--text-secondary)]">{brief.page_type}{brief.target_words ? ` · about ${num(brief.target_words)} words` : ""}</div>
      </div>
      <p>{brief.angle}</p>
      <List title="Sections" items={brief.sections} />
      <List title="Questions to answer" items={brief.questions} />
      <List title="Cover" items={brief.entities} />
      {brief.link_from?.length ? <List title="Link to it from" items={brief.link_from.map((l) => `${shortPage(l.url)} — “${l.anchor_idea}”`)} /> : null}
      <List title="Avoid" items={brief.avoid} />
      <div className="flex items-center gap-3 text-xs text-[var(--text-tertiary)]">
        <button type="button" onClick={() => void navigator.clipboard.writeText(asText(brief)).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })} className="rounded-lg border border-[var(--border)] bg-white px-2 py-1 font-semibold text-[var(--text)]">{copied ? "Copied" : "Copy brief"}</button>
        <span>{DEPTH[brief.depth]} · ${brief.cost_usd.toFixed(2)}{brief.page_read === false ? " · the closest page could not be read" : ""}</span>
      </div>
    </div>
  );
}

function TopicPane({ client, label, dismissed, onDismiss, onCalendar }: { client: Client; label: string; dismissed: boolean; onDismiss: () => void; onCalendar: () => void }) {
  const [d, setD] = useState<TopicDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<ContentDepthChoice>("quick");
  const [pending, start] = useTransition();
  const now = useRef(`${client.id}|${label}`);
  now.current = `${client.id}|${label}`;
  const load = () => {
    const asked = now.current;
    return topicDetailAction(client.id, label).then((r) => {
      if (now.current !== asked) return; // a reply for a subject no longer open
      if (r.ok) {
        setD(r.value);
        setError(null);
      } else setError(r.error);
    });
  };
  useEffect(() => {
    setD(null);
    setError(null);
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client.id, label]);
  const running = d?.draft?.status === "running";
  useEffect(() => {
    if (!running) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const write = () =>
    start(async () => {
      setError(null);
      const r = await draftAction(client.id, "tbrief", label, depth);
      if (!r.ok) setError(r.error);
      else await load();
    });
  const brief = d?.draft;
  return (
    <div className="space-y-4 text-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-lg font-bold">{label}</p>
          {d ? <p className="text-xs text-[var(--text-secondary)]">{d.topic.content_type}{d.topic.next_to ? ` · sits next to ${d.topic.next_to}` : ""}</p> : null}
        </div>
        <button type="button" onClick={onDismiss} disabled={pending} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1 text-xs font-semibold disabled:opacity-50">{dismissed ? "Restore" : "Not in scope"}</button>
      </div>
      {error ? <p role="alert" className="font-semibold text-red-700">{error}</p> : null}
      {!d && !error ? <p className="text-[var(--text-secondary)]"><Spinner />Reading the topic…</p> : null}
      {d ? (
        <>
          <div className="rounded-lg bg-[var(--bg)] p-3 text-xs"><p>{d.topic.why}</p></div>
          <div>
            <h3 className="font-bold">Searches in this subject</h3>
            <p className="text-xs text-[var(--text-tertiary)]">The data on file for each. “Waiting” means no volume has been bought for it yet.</p>
            <div className="overflow-x-auto">
              <table className="mt-1 w-full text-xs">
                <thead><tr><th className={th}>Search</th><th className={th}>Volume</th><th className={th}>Difficulty</th><th className={th}>Shown</th><th className={th}>Where it stands</th></tr></thead>
                <tbody>
                  {d.searches.map((x) => (
                    <tr key={x.term} className="border-t border-[var(--border)] align-top">
                      <td className="px-3 py-2 font-semibold">{x.term}</td>
                      <td className={td}>{x.volume != null ? num(x.volume) : <span className="text-[var(--text-tertiary)]">waiting</span>}</td>
                      <td className={td}>{x.difficulty ?? "–"}</td>
                      <td className={td}>{x.impressions ? `${num(x.impressions)}${x.position != null ? ` · pos ${x.position}` : ""}` : "–"}</td>
                      <td className="px-3 py-2 text-[var(--text-secondary)]">{[x.gap ? "A gap on the list" : null, x.tracked ? "On the watchlist" : null].filter(Boolean).join(", ") || "–"}</td>
                    </tr>
                  ))}
                  {d.searches.length === 0 ? <tr><td colSpan={5} className="px-3 py-2 text-[var(--text-secondary)]">The model listed no searches for this subject.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </div>
          <AddToCalendar client={client} canEdit={d.can_edit} status={d.calendar ?? undefined} kind="new_page" title={brief?.status === "done" && brief.working_title ? brief.working_title : label} target={label} sourceArea="topic" sourceKey={label} onAdded={() => { void load(); onCalendar(); }} />
          <div className="space-y-2 rounded-lg border border-[var(--border)] p-3">
            <h3 className="font-bold">Content brief</h3>
            <p className="text-xs text-[var(--text-tertiary)]">The model drafts one brief for the whole subject from the searches above. A draft: nothing is sent anywhere and it uses no page allowance.</p>
            <AskModel ready={d.model_ready} depth={depth} onDepth={setDepth} busy={pending || running} again={brief?.status === "done"} label="Write a brief" onRun={write} />
            {brief?.status === "failed" ? <p role="alert" className="text-xs font-semibold text-red-700">{brief.error}</p> : null}
            {brief?.status === "done" ? <BriefBody brief={brief} heading={label} /> : null}
          </div>
        </>
      ) : null}
    </div>
  );
}

const PRIORITY = { high: "bg-red-100 text-red-800", medium: "bg-amber-100 text-amber-900", low: "bg-gray-100 text-gray-700" } as const;

function Topics({ client }: { client: Client }) {
  const [t, setT] = useState<TopicsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [depth, setDepth] = useState<ContentDepthChoice>("quick");
  const [open, setOpen] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const load = () => topicsAction(client.id).then((r) => (r.ok ? setT(r.value) : setError(r.error)));
  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [client.id]);
  const running = t?.draft?.status === "running";
  useEffect(() => {
    if (!running) return;
    const i = setInterval(load, 2500);
    return () => clearInterval(i);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running]);
  const run = () =>
    start(async () => {
      setError(null);
      const r = await draftAction(client.id, "topics", "site", depth);
      if (!r.ok) setError(r.error);
      else await load();
    });
  const dismiss = (label: string, restore: boolean) =>
    start(async () => {
      const r = await dismissTopicAction(client.id, label, restore);
      if (!r.ok) setError(r.error);
      else await load();
    });
  const draft = t?.draft;
  // A subject set aside is gone at once, without asking the model again: the saved draft still holds it, so it is hidden here.
  const hidden = new Set((t?.dismissed ?? []).map((d) => d.toLowerCase()));
  const topics = draft?.topics?.filter((tp) => !hidden.has(tp.label.toLowerCase()));
  return (
    <section className={`${card} p-5`}>
      <h2 className="text-lg font-bold">Missing topics</h2>
      <p className="text-xs text-[var(--text-tertiary)]">
        Whole subjects next to what the site is known for that no page covers. The model reads the watchlist&apos;s topics, the titles of the pages Google shows most, and the searches the site is shown for. Dismiss a subject that is not in scope and it is never suggested again.
      </p>
      <div className="mt-3"><AskModel ready={t?.model_ready ?? false} depth={depth} onDepth={setDepth} busy={pending || running} again={draft?.status === "done"} label="Find missing topics" onRun={run} /></div>
      {error ? <p role="alert" className="mt-2 text-sm font-semibold text-red-700">{error}</p> : null}
      {draft?.status === "failed" ? <p role="alert" className="mt-2 text-sm font-semibold text-red-700">{draft.error}</p> : null}
      {draft?.status === "done" && topics ? (
        <div className="mt-3 space-y-2">
          {topics.length === 0 ? <p className="text-sm font-semibold text-green-700">Clean: nothing new to suggest.</p> : null}
          {topics.map((tp) => (
            <div key={tp.label} className="cursor-pointer rounded-lg border border-[var(--border)] p-3 text-sm hover:bg-[var(--bg)]" onClick={() => setOpen(tp.label)}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-bold">{tp.label}</span>
                <span className={`rounded px-1.5 py-0.5 text-[0.7rem] font-semibold ${PRIORITY[tp.priority]}`}>{tp.priority}</span>
                {tp.content_type ? <span className="text-xs text-[var(--text-tertiary)]">{tp.content_type}</span> : null}
                <button type="button" disabled={pending} onClick={(e) => { e.stopPropagation(); dismiss(tp.label, false); }} className="ml-auto rounded-lg border border-[var(--border)] bg-white px-2 py-0.5 text-xs font-semibold disabled:opacity-50">Not in scope</button>
              </div>
              <p className="mt-1">{tp.why}</p>
              {tp.example_searches.length ? <p className="mt-1 text-xs text-[var(--text-secondary)]">Searches: {tp.example_searches.join(" · ")}</p> : null}
              {tp.next_to ? <p className="text-xs text-[var(--text-tertiary)]">Sits next to: {tp.next_to}</p> : null}
              <p className="mt-1 text-xs font-semibold text-[var(--brand-dark)]">Open for its searches, a brief and the calendar</p>
            </div>
          ))}
          <p className="text-xs text-[var(--text-tertiary)]">{DEPTH[draft.depth]} · ${draft.cost_usd.toFixed(2)} · read {draft.pages_used} pages and {draft.searches_used} searches.</p>
        </div>
      ) : null}
      {t && t.dismissed.length > 0 ? (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer font-semibold">Not in scope ({t.dismissed.length})</summary>
          <ul className="mt-1 space-y-1">{t.dismissed.map((d) => <li key={d} className="flex items-center gap-2">{d}<button type="button" disabled={pending} onClick={() => dismiss(d, true)} className="rounded-lg border border-[var(--border)] bg-white px-2 py-0.5 font-semibold disabled:opacity-50">Restore</button></li>)}</ul>
        </details>
      ) : null}
      <SidePane open={!!open} label="Missing topic" onClose={() => setOpen(null)}>
        {open ? <TopicPane client={client} label={open} dismissed={hidden.has(open.toLowerCase())} onDismiss={() => { dismiss(open, hidden.has(open.toLowerCase())); setOpen(null); }} onCalendar={() => undefined} /> : null}
      </SidePane>
    </section>
  );
}

export function ContentGaps({ client, q, ignored, data, error }: { client: Client; q: string; ignored: boolean; data: Gaps | null; error: string | null }) {
  const router = useRouter();
  const [search, setSearch] = useState(q);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const go = (query = q, showIgnored = ignored) => {
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (showIgnored) params.set("ignored", "1");
    router.push(`/${client.slug}/content-gaps${params.size ? `?${params}` : ""}`);
  };
  const gap = data?.gaps.find((g) => g.term === open) ?? null;
  const c = data?.counts ?? {};

  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Content gaps</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">Searches people make that the site has no page for, ranked by the searches a page could compete for.</p>
      </header>

      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {data?.blocked ? <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">{data.blocked}</p> : null}

      {data && !data.blocked ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi label="Gaps to fill" value={num(c.gaps)} note={`checked against ${num(c.pages_searched)} pages`} />
            <Kpi label="Shown in Google" value={num(c.searched)} note="searches the site is shown for with no page about them" />
            <Kpi label="Competitors rank" value={num(c.competitor)} note="top-ten terms of the competitors named in settings" />
            <Kpi label="Searches to compete for" value={num(c.opportunity)} note="a month, across the gaps" />
          </div>

          <Topics client={client} />

          <form className="flex flex-wrap items-center gap-2 text-sm" onSubmit={(e) => { e.preventDefault(); go(search.trim()); }} role="search">
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Find a gap: a search, or part of a nearby page's address or title" aria-label="Find a gap" className="min-w-[20rem] flex-1 rounded-lg border border-[var(--border)] bg-white px-3 py-2" />
            <button type="submit" className="rounded-lg border border-[var(--border)] bg-white px-4 py-2 font-semibold">Find</button>
            {q ? <button type="button" onClick={() => { setSearch(""); go(""); }} className="text-xs font-semibold underline">Clear</button> : null}
            <button type="button" onClick={() => go(q, !ignored)} className="ml-auto text-xs font-semibold underline">{ignored ? "Back to the gaps" : `Show ignored (${data.ignored_total})`}</button>
          </form>

          <section className={card}>
            <h2 className="px-5 pt-4 text-lg font-bold">{ignored ? "Ignored gaps" : q ? `Gaps matching “${q}”` : "Gaps, most to compete for first"}</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">Open a gap to see the pages closest to it, who ranks for it, and to have the model draft a brief.</p>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-sm">
                <thead><tr><th className={th}>Search</th><th className={th}>Where it came from</th><th className={th}>Volume</th><th className={th}>Difficulty</th><th className={th}>To compete for</th><th className={th}>Shown</th><th className={th}>Calendar</th></tr></thead>
                <tbody>
                  {data.gaps.map((g) => (
                    <tr key={g.term} className="cursor-pointer border-t border-[var(--border)] align-top hover:bg-[var(--bg)]" onClick={() => setOpen(g.term)}>
                      <td className="max-w-sm px-3 py-2"><div className="font-semibold">{g.term}</div><div className="text-xs text-[var(--text-tertiary)]">{g.action}</div></td>
                      <td className="px-3 py-2 text-xs text-[var(--text-secondary)]">{g.sources.map((s) => SOURCE[s]).join(", ")}</td>
                      <td className={td}>{g.priced ? num(g.volume) : <span className="text-xs text-[var(--text-tertiary)]">waiting</span>}</td>
                      <td className={td}>{g.difficulty != null ? Math.round(g.difficulty) : "–"}</td>
                      <td className={`${td} font-semibold`}>{g.opportunity ? num(g.opportunity) : "–"}</td>
                      <td className={td}>{g.impressions ? `${num(g.impressions)}${g.position != null ? ` · pos ${g.position}` : ""}` : "–"}</td>
                      <td className="px-3 py-2"><StatusChip status={data.calendar?.[g.term]} /></td>
                    </tr>
                  ))}
                  {data.gaps.length === 0 ? <tr><td colSpan={7} className={`px-5 py-4 font-semibold ${q || ignored ? "text-[var(--text-secondary)]" : "text-green-700"}`}>{ignored ? "Nothing is ignored." : q ? `No gap matches “${q}”.` : "Clean: every search with demand has a page."}</td></tr> : null}
                </tbody>
              </table>
            </div>
            {data.gaps_total && data.gaps_total > data.gaps.length ? <p className="px-5 pb-3 text-xs text-[var(--text-tertiary)]">The first {data.gaps.length} of {data.gaps_total}. Find a gap to see the rest.</p> : null}
          </section>
          <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-tertiary)]">{data.notes.map((n) => <li key={n}>{n}</li>)}</ul>
        </>
      ) : null}

      <SidePane open={!!gap} label="Content gap" onClose={() => setOpen(null)}>
        {gap ? <BriefPane client={client} gap={gap} ready={data?.model_ready ?? false} canEdit={data?.can_edit ?? false} onCalendar={data?.calendar?.[gap.term]} onRefresh={() => router.refresh()} onChanged={() => { setOpen(null); router.refresh(); }} /> : null}
      </SidePane>
    </section>
  );
}
