"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";

import { ignoreInlinkAction, restoreInlinkAction, setInlinkStateAction, verifyInlinkAction, writeInlinkSentenceAction } from "@/app/(app)/[clientSlug]/inlinks/actions";
import type { Client } from "@/lib/api";
import type { InData, InStatus, InSuggestion, InTarget } from "@/lib/inlinks";

// The split view from the design handoff: pages to work on down the left, and for the chosen page one numbered card per link to add.
// What the engine knows is unchanged; this screen only decides what the team sees first.

type Status = InStatus | "checking";
type Filter = "todo" | "progress" | "done" | "all";
type Written = { sentence: string; anchor: string };

const INK = "#0a0c0f";
const DARK = "#223540";
const TEAL = "#00a99d";
const RED = { background: "oklch(0.965 0.025 25)", color: "oklch(0.48 0.17 25)" };
const AMBER = { background: "oklch(0.97 0.045 85)", color: "oklch(0.42 0.1 65)" };
const heading = "font-[family-name:var(--font-heading)] font-bold";
const WHY_KEY = "organiciq.inlinks.showWhy";

const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const num = (n: number) => n.toLocaleString("en-US");
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const keyOf = (target: string, source: string) => `${target}|${source}`;
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** The same page however its address is written: with or without www, a trailing slash, a query. */
function sameAddress(a: string, b: string): boolean {
  const clean = (u: string) => u.trim().toLowerCase().replace(/^https?:\/\/(www\.)?/, "").replace(/[?#].*$/, "").replace(/\/+$/, "");
  return clean(a) === clean(b);
}

function when(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso);
  const minutes = (Date.now() - then.getTime()) / 60000;
  if (minutes < 2) return "just now";
  if (minutes < 60) return `${Math.round(minutes)} minutes ago`;
  return `on ${then.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })}`;
}

/** The link texts a person can pick between, the engine's choice first. */
function candidates(s: InSuggestion): string[] {
  const seen = new Set<string>();
  // A generic label ("this guide") or a bare address says nothing about where the link leads, so it is never offered.
  const others = s.anchor_alternates.filter((a) => a.type !== "generic" && a.type !== "naked_url").map((a) => a.anchor);
  return [s.chosen_anchor, s.anchor_in_paragraph, s.anchor_type === "generic" ? null : s.suggested_anchor, ...others]
    .filter((a): a is string => !!a && !a.toLowerCase().startsWith("http"))
    .filter((a) => (seen.has(a.toLowerCase()) ? false : (seen.add(a.toLowerCase()), true)))
    .slice(0, 4);
}

/** Where the link goes and how to show it: words already in a sentence of the page, or a sentence to add beside a paragraph. */
function placement(s: InSuggestion, anchor: string) {
  const text = s.paragraph?.text ?? "";
  const under = s.paragraph?.heading ? ` under “${s.paragraph.heading}”` : "";
  const at = anchor ? text.toLowerCase().indexOf(anchor.toLowerCase()) : -1;
  if (at >= 0) {
    // The sentence the words sit in, not the whole paragraph.
    const starts = [0, ...Array.from(text.matchAll(/[.!?]["”’)]?\s+/g), (m) => (m.index ?? 0) + m[0].length)];
    const from = starts.filter((i) => i <= at).pop() ?? 0;
    const to = starts.find((i) => i >= at + anchor.length) ?? text.length;
    return { existing: true, instruction: `Link these words in the paragraph${under}:`, pre: text.slice(from, at), mark: text.slice(at, at + anchor.length), post: text.slice(at + anchor.length, to).trimEnd(), near: "" };
  }
  if (text) {
    const opening = text.split(/\s+/).slice(0, 28).join(" ");
    return { existing: false, instruction: `Add a sentence with this link after the paragraph${under} that starts:`, pre: "", mark: anchor, post: "", near: opening.length < text.length ? `${opening}…` : opening };
  }
  return { existing: false, instruction: "Add a sentence with this link where the page covers this subject:", pre: "", mark: anchor, post: "", near: "" };
}

const STATUS_PILL: Record<Status, { label: string; background: string; color: string }> = {
  todo: { label: "To do", background: "#eef0f1", color: "#4a5560" },
  added: { label: "Added · not checked", background: "#e9fedc", color: "#2f5a00" },
  checking: { label: "Checking…", background: "#eef0f1", color: "#4a5560" },
  live: { label: "Live ✓", background: "#c6f2ed", color: "#00665f" },
  skipped: { label: "Skipped", background: "#eef0f1", color: "#909a9f" },
};

export function InlinkSuggester({ client, q, data, error }: { client: Client; q: string; data: InData | null; error: string | null }) {
  const router = useRouter();
  const wanted = useSearchParams().get("target");
  const [, start] = useTransition();
  const targets = useMemo(() => data?.targets ?? [], [data]);

  // What the server last said, overlaid with what was done on this screen since. A fresh load replaces the overlay.
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [anchors, setAnchors] = useState<Record<string, string>>({});
  const [checked, setChecked] = useState<Record<string, { at: string; anchor: string | null }>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [ignored, setIgnored] = useState<Record<string, boolean>>({});
  const [sentences, setSentences] = useState<Record<string, Written | null>>({});
  const [writing, setWriting] = useState<Record<string, boolean>>({});
  useEffect(() => {
    setSentences({});
    setStatus({});
    setAnchors({});
    setChecked({});
    setNotes({});
    setIgnored({});
  }, [data]);

  const [selected, setSelected] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>(q ? "all" : "todo");
  const [query, setQuery] = useState(wanted ? "" : q);
  const [how, setHow] = useState(false);
  const [showIgnored, setShowIgnored] = useState(false);
  const [showWhy, setShowWhy] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  useEffect(() => {
    try {
      setShowWhy(window.localStorage.getItem(WHY_KEY) === "1");
    } catch {
      /* A browser that refuses storage keeps the default. */
    }
  }, []);
  const toggleWhy = (on: boolean) => {
    setShowWhy(on);
    try {
      window.localStorage.setItem(WHY_KEY, on ? "1" : "0");
    } catch {
      /* Not kept for next time. */
    }
  };

  const statusOf = (t: InTarget, s: InSuggestion): Status => status[keyOf(t.target_url, s.source_url)] ?? s.status ?? "todo";
  const anchorOf = (t: InTarget, s: InSuggestion): string => anchors[keyOf(t.target_url, s.source_url)] ?? candidates(s)[0] ?? "";
  /** The sentence written for this link, while it still carries the link text now chosen. */
  const sentenceOf = (t: InTarget, s: InSuggestion): Written | null => {
    const k = keyOf(t.target_url, s.source_url);
    const held = k in sentences ? sentences[k] : s.sentence && s.sentence_anchor ? { sentence: s.sentence, anchor: s.sentence_anchor } : null;
    return held && held.anchor.toLowerCase() === anchorOf(t, s).toLowerCase() ? held : null;
  };
  const pageState = (t: InTarget): "todo" | "progress" | "done" => {
    const all = t.suggestions.map((s) => statusOf(t, s));
    if (all.every((x) => x === "live" || x === "skipped")) return "done";
    return all.some((x) => x !== "todo") ? "progress" : "todo";
  };

  const visible = targets.filter((t) => !ignored[t.target_url]);
  // Pages nothing links to yet come first for the same demand.
  const weight = (t: InTarget) => t.impressions * (t.inbound === 0 ? 1.6 : 1);
  const sorted = [...visible].sort((a, b) => weight(b) - weight(a));
  const FILTERS: { key: Filter; label: string; keep: (t: InTarget) => boolean }[] = [
    { key: "todo", label: "To do", keep: (t) => pageState(t) !== "done" },
    { key: "progress", label: "In progress", keep: (t) => pageState(t) === "progress" },
    { key: "done", label: "Done", keep: (t) => pageState(t) === "done" },
    { key: "all", label: "All", keep: () => true },
  ];
  const needle = query.trim().toLowerCase();
  const matches = (t: InTarget) => !needle || `${t.target_url} ${t.target_title} ${t.title} ${t.queries.join(" ")}`.toLowerCase().includes(needle);
  const keep = FILTERS.find((f) => f.key === filter)!.keep;
  const rows = sorted.filter((t) => keep(t) && matches(t));

  const current =
    sorted.find((t) => t.target_url === selected) ??
    (wanted ? sorted.find((t) => sameAddress(t.target_url, wanted)) : undefined) ??
    rows[0] ??
    sorted[0] ??
    null;

  const every = visible.flatMap((t) => t.suggestions.map((s) => statusOf(t, s)));
  const stats = [
    { n: visible.filter((t) => pageState(t) !== "done").length, label: "pages need links", color: INK },
    { n: every.filter((x) => x === "todo").length, label: "links to add", color: INK },
    { n: every.filter((x) => x === "added" || x === "checking").length, label: "added, not checked", color: INK },
    { n: every.filter((x) => x === "live").length, label: "confirmed live", color: "#00857b" },
  ];

  const copy = (id: string, text: string) => {
    void navigator.clipboard?.writeText(text);
    setCopied(id);
    setTimeout(() => setCopied((c) => (c === id ? null : c)), 1500);
  };
  const say = (k: string, text: string) => setNotes((n) => ({ ...n, [k]: text }));

  /** Show the change at once, save it, and put it back if the save fails. */
  const move = (t: InTarget, s: InSuggestion, to: "todo" | "added" | "skipped") => {
    const k = keyOf(t.target_url, s.source_url);
    const before = statusOf(t, s);
    setStatus((m) => ({ ...m, [k]: to }));
    say(k, "");
    start(async () => {
      const r = await setInlinkStateAction(client.id, s.source_url, t.target_url, { status: to });
      if (!r.ok) {
        setStatus((m) => ({ ...m, [k]: before }));
        say(k, r.error);
      }
    });
  };
  const write = (t: InTarget, s: InSuggestion, anchor: string) => {
    const k = keyOf(t.target_url, s.source_url);
    setWriting((m) => ({ ...m, [k]: true }));
    say(k, "");
    start(async () => {
      const r = await writeInlinkSentenceAction(client.id, s.source_url, t.target_url, anchor);
      setWriting((m) => ({ ...m, [k]: false }));
      if (r.ok && r.value.ok) setSentences((m) => ({ ...m, [k]: { sentence: r.value.ok ? r.value.sentence : "", anchor: r.value.ok ? r.value.anchor : "" } }));
      else say(k, r.ok ? (r.value.ok ? "" : r.value.reason) : r.error);
    });
  };
  const choose = (t: InTarget, s: InSuggestion, anchor: string) => {
    const k = keyOf(t.target_url, s.source_url);
    const before = anchorOf(t, s);
    // A sentence written around the old words is written again around the new ones.
    const rewrite = !!sentenceOf(t, s) && !placement(s, anchor).existing;
    setAnchors((m) => ({ ...m, [k]: anchor }));
    setSentences((m) => ({ ...m, [k]: null }));
    start(async () => {
      const r = await setInlinkStateAction(client.id, s.source_url, t.target_url, { anchor });
      if (!r.ok) {
        setAnchors((m) => ({ ...m, [k]: before }));
        say(k, r.error);
      } else if (rewrite) write(t, s, anchor);
    });
  };
  const check = (t: InTarget, s: InSuggestion) => {
    const k = keyOf(t.target_url, s.source_url);
    setStatus((m) => ({ ...m, [k]: "checking" }));
    say(k, "");
    start(async () => {
      const r = await verifyInlinkAction(client.id, s.source_url, t.target_url);
      if (r.ok && r.value.checked && r.value.found) {
        setStatus((m) => ({ ...m, [k]: "live" }));
        setChecked((m) => ({ ...m, [k]: { at: new Date().toISOString(), anchor: r.value.anchor } }));
        return;
      }
      setStatus((m) => ({ ...m, [k]: "added" }));
      say(k, !r.ok ? r.error : !r.value.checked ? (r.value.error ?? "The page could not be checked.") : "Not on the page yet. If it was just published, the page may still be cached.");
    });
  };
  const ignorePage = (t: InTarget) => {
    const next = rows.find((x) => x.target_url !== t.target_url) ?? sorted.find((x) => x.target_url !== t.target_url);
    setIgnored((m) => ({ ...m, [t.target_url]: true }));
    setSelected(next ? next.target_url : null);
    start(async () => {
      const r = await ignoreInlinkAction(client.id, client.slug, t.target_url, null);
      if (r.ok) router.refresh();
      else setIgnored((m) => ({ ...m, [t.target_url]: false }));
    });
  };
  const restorePage = (id: string) =>
    start(async () => {
      const r = await restoreInlinkAction(client.id, client.slug, id);
      if (r.ok) router.refresh();
    });
  const searchAll = () => router.push(`/${client.slug}/inlinks?${new URLSearchParams({ q: query.trim() })}`);

  const linksText = (t: InTarget) => (t.inbound === 0 ? "No links yet" : `${t.inbound} of ${t.wanted} links`);

  return (
    <section className="flex h-[calc(100vh-7.5rem)] min-h-[36rem] flex-col overflow-hidden rounded-xl border border-[#e8e8e8] bg-[#f6f7f7] text-sm text-[#171a22]">
      <header className="flex flex-none flex-wrap items-center justify-between gap-x-6 gap-y-3 border-b border-[#e8e8e8] bg-white px-6 py-4">
        <div>
          <h1 className={`${heading} text-2xl`} style={{ color: INK }}>Inlink suggester</h1>
          <p className="mt-0.5 text-[13px] text-[#4a5560]">Pages that need internal links, and exactly where to add each one.</p>
        </div>
        {data ? (
          <dl className="flex items-center gap-7">
            {stats.map((s) => (
              <div key={s.label}>
                <dd className={`${heading} text-[22px] tabular-nums`} style={{ color: s.color }}>{num(s.n)}</dd>
                <dt className="whitespace-nowrap text-xs text-[#7a838c]">{s.label}</dt>
              </div>
            ))}
          </dl>
        ) : null}
      </header>

      {error ? <p role="alert" className="m-6 rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}
      {!error && !data ? <p className="m-6 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">This site has not been crawled yet, or has too few pages, so there is nothing to suggest. Pull data on the Connections page starts a crawl.</p> : null}

      {data ? (
        <div className="flex min-h-0 flex-1">
          {/* Left: the pages, most worth working on first. */}
          <div className="flex w-[400px] flex-none flex-col border-r border-[#e8e8e8] bg-white">
            <div className="flex flex-col gap-2.5 border-b border-[#eef0f1] px-4 pb-2.5 pt-3.5">
              <label className="flex items-center gap-2 rounded-[10px] border border-[#e3e6e8] bg-white px-3">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#7a838c" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Find a page by address, title or search"
                  aria-label="Find a page"
                  className="flex-1 border-0 bg-transparent py-[9px] text-[13px] outline-none"
                />
              </label>
              <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Show pages">
                {FILTERS.map((f) => {
                  const on = f.key === filter;
                  return (
                    <button
                      key={f.key}
                      type="button"
                      role="tab"
                      aria-selected={on}
                      onClick={() => setFilter(f.key)}
                      className="rounded-full border px-[11px] py-1 text-xs font-semibold"
                      style={on ? { background: DARK, borderColor: DARK, color: "#fff" } : { background: "#fff", borderColor: "#e3e6e8", color: "#171a22" }}
                    >
                      {f.label} <span className="font-medium opacity-65">{visible.filter(f.keep).length}</span>
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="flex-1 overflow-y-auto">
              {rows.map((t) => {
                const sts = t.suggestions.map((s) => statusOf(t, s));
                const done = sts.filter((x) => x === "live" || x === "added" || x === "checking").length;
                const total = sts.filter((x) => x !== "skipped").length;
                const on = current?.target_url === t.target_url;
                return (
                  <button
                    key={t.target_url}
                    type="button"
                    onClick={() => setSelected(t.target_url)}
                    aria-current={on ? "true" : undefined}
                    className={`flex w-full items-center gap-3 border-b border-[#f1f2f3] px-4 py-3 text-left ${on ? "" : "hover:bg-[#f8f8f8]"}`}
                    style={on ? { background: "#eef8f7", boxShadow: `inset 3px 0 0 ${TEAL}` } : undefined}
                  >
                    <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
                      <div className="truncate text-[13px] font-semibold" style={{ color: INK }}>{t.target_title}</div>
                      <div className="truncate text-[11px] text-[#7a838c]">{shortPage(t.target_url)}</div>
                      <div className="flex items-center gap-1.5 text-[11px] text-[#7a838c]">
                        <span className="rounded-full px-[7px] font-semibold" style={t.inbound === 0 ? RED : AMBER}>{linksText(t)}</span>
                        <span>{num(t.impressions)} impressions</span>
                      </div>
                    </div>
                    <div className="flex flex-none flex-col items-end gap-1">
                      <span className="text-xs font-semibold" style={{ color: done && done === total ? "#00665f" : INK }}>{done ? `${done} of ${total} added` : `${total} to add`}</span>
                      <span className="block h-1 w-14 overflow-hidden rounded-sm bg-[#eef0f1]"><span className="block h-full" style={{ width: `${total ? (done / total) * 100 : 100}%`, background: TEAL }} /></span>
                    </div>
                  </button>
                );
              })}
              {rows.length === 0 ? (
                <div className="px-4 py-7 text-center text-[13px] text-[#7a838c]">
                  {needle ? "No pages match. Try part of the address or a search the page ranks for." : filter === "todo" ? "Clean: no page is waiting for links." : "No pages here yet."}
                  {needle ? (
                    <div className="mt-3">
                      <button type="button" onClick={searchAll} className="font-semibold text-[#00857b] hover:underline">Look through every crawled page</button>
                    </div>
                  ) : null}
                </div>
              ) : null}
              {q ? (
                <div className="border-t border-[#eef0f1] px-4 py-3 text-xs text-[#4a5560]">
                  Showing pages matching “{q}”, including ones that already have enough links.{" "}
                  <button type="button" onClick={() => router.push(`/${client.slug}/inlinks`)} className="font-semibold text-[#00857b] hover:underline">Back to the full list</button>
                </div>
              ) : null}
              <div className="border-t border-[#eef0f1]">
                <button type="button" onClick={() => setHow((v) => !v)} aria-expanded={how} className="flex w-full justify-between px-4 py-3 text-xs font-semibold text-[#4a5560]">
                  How suggestions are picked<span>{how ? "−" : "+"}</span>
                </button>
                {how ? (
                  <div className="flex flex-col gap-1.5 px-4 pb-3.5 text-xs text-[#4a5560]">
                    <div>• Linking pages are at least {data.min_similarity ?? 50}% alike in subject and already earn clicks.</div>
                    <div>• Contact, about and utility pages are never used. Blog posts are preferred. A customer review is never where a link goes.</div>
                    <div>• The anchor is a short phrase, never “read more” or the brand name alone.</div>
                    <div>• Pages with search demand and fewer than {data.wanted_links ?? 5} editorial links come first. Crawl of {day(data.crawl_date)}.</div>
                    <label className="mt-1 flex items-center gap-2 font-semibold">
                      <input type="checkbox" checked={showWhy} onChange={(e) => toggleWhy(e.target.checked)} />
                      Show why each linking page was picked
                    </label>
                  </div>
                ) : null}
              </div>
              {data.ignored.length > 0 ? (
                <div className="border-t border-[#eef0f1]">
                  <button type="button" onClick={() => setShowIgnored((v) => !v)} aria-expanded={showIgnored} className="flex w-full justify-between px-4 py-3 text-xs font-semibold text-[#4a5560]">
                    Ignored pages <span>{data.ignored.length} {showIgnored ? "−" : "+"}</span>
                  </button>
                  {showIgnored ? (
                    <ul className="px-4 pb-3.5 text-xs text-[#4a5560]">
                      {data.ignored.map((i) => (
                        <li key={i.id} className="flex items-center gap-3 py-1">
                          <span className="min-w-0 flex-1 truncate">{shortPage(i.target)}</span>
                          <button type="button" onClick={() => restorePage(i.id)} className="font-semibold text-[#00857b] hover:underline">Restore</button>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>

          {/* Right: the chosen page, and one card per link to add. */}
          <div className="min-w-0 flex-1 overflow-y-auto">
            {current ? (
              <Detail
                key={current.target_url}
                t={current}
                linksText={linksText(current)}
                statusOf={(s) => statusOf(current, s)}
                anchorOf={(s) => anchorOf(current, s)}
                sentenceOf={(s) => sentenceOf(current, s)}
                writingOf={(s) => !!writing[keyOf(current.target_url, s.source_url)]}
                onWrite={(s) => write(current, s, anchorOf(current, s))}
                checkedOf={(s) => checked[keyOf(current.target_url, s.source_url)]}
                noteOf={(s) => notes[keyOf(current.target_url, s.source_url)]}
                showWhy={showWhy}
                copied={copied}
                onCopy={copy}
                onMove={(s, to) => move(current, s, to)}
                onChoose={(s, a) => choose(current, s, a)}
                onCheck={(s) => check(current, s)}
                onIgnore={() => ignorePage(current)}
              />
            ) : (
              <div className="p-10 text-center text-[13px] text-[#7a838c]">{q ? `No crawled page matches “${q}”, or nothing alike is left to link from it.` : "Clean: every page that earns search traffic has enough links, or nothing alike is left to link from."}</div>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function Detail({
  t, linksText, statusOf, anchorOf, sentenceOf, writingOf, onWrite, checkedOf, noteOf, showWhy, copied, onCopy, onMove, onChoose, onCheck, onIgnore,
}: {
  t: InTarget;
  linksText: string;
  statusOf: (s: InSuggestion) => Status;
  anchorOf: (s: InSuggestion) => string;
  sentenceOf: (s: InSuggestion) => Written | null;
  writingOf: (s: InSuggestion) => boolean;
  onWrite: (s: InSuggestion) => void;
  checkedOf: (s: InSuggestion) => { at: string; anchor: string | null } | undefined;
  noteOf: (s: InSuggestion) => string | undefined;
  showWhy: boolean;
  copied: string | null;
  onCopy: (id: string, text: string) => void;
  onMove: (s: InSuggestion, to: "todo" | "added" | "skipped") => void;
  onChoose: (s: InSuggestion, anchor: string) => void;
  onCheck: (s: InSuggestion) => void;
  onIgnore: () => void;
}) {
  const open = t.suggestions.filter((s) => statusOf(s) === "todo").length;
  const live = t.suggestions.filter((s) => statusOf(s) === "live").length;
  const checklist =
    `Internal links for ${t.target_url}\n` +
    t.suggestions
      .filter((s) => statusOf(s) !== "skipped")
      .map((s, i) => {
        const anchor = anchorOf(s);
        const place = placement(s, anchor);
        const written = place.existing ? null : sentenceOf(s);
        const where = place.existing
          ? `link the words “${anchor}” in the sentence “${`${place.pre}${place.mark}${place.post}`.trim()}”`
          : written
            ? `after the paragraph that starts “${place.near}”, add the sentence “${written.sentence}” and link the words “${written.anchor}”`
            : `${place.instruction.replace(/:$/, "")}${place.near ? ` “${place.near}”` : ""}. Link text “${anchor}”`;
        return `${i + 1}. On ${s.source_url}: ${where}`;
      })
      .join("\n");
  return (
    <>
      <div className="flex items-start justify-between gap-5 border-b border-[#e8e8e8] bg-white px-7 py-[18px]">
        <div className="min-w-0">
          <div className="text-[11px] font-bold uppercase tracking-[.12em] text-[#7a838c]">Send links to</div>
          <h2 className={`${heading} mt-0.5 text-xl`} style={{ color: INK }}>{t.target_title}</h2>
          <a href={t.target_url} target="_blank" rel="noreferrer" className="break-all text-[13px] text-[#00857b] hover:underline">{t.target_url.replace(/^https?:\/\//, "")}</a>
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-[#4a5560]">
            {t.queries.length > 0 && t.position != null ? <span>Ranks <strong style={{ color: INK }}>#{t.position}</strong> for “{t.queries[0]}”</span> : null}
            <span><strong style={{ color: INK }}>{num(t.impressions)}</strong> impressions / 3 mo</span>
            <span className="font-semibold" style={{ color: t.inbound === 0 ? RED.color : AMBER.color }}>{linksText}</span>
          </div>
        </div>
        <div className="flex flex-none flex-col items-end gap-2">
          <button type="button" onClick={() => onCopy("all", checklist)} className="rounded-full px-4 py-[9px] text-[13px] font-semibold text-white hover:bg-[#00a99d]" style={{ background: copied === "all" ? TEAL : DARK }}>
            {copied === "all" ? "Checklist copied ✓" : "Copy as checklist"}
          </button>
          <button type="button" onClick={onIgnore} className="text-xs font-semibold text-[#7a838c] hover:underline">Ignore this page</button>
        </div>
      </div>

      <div className="flex flex-col gap-3 px-7 pb-8 pt-[18px]">
        <div className="flex items-baseline justify-between">
          <h3 className={`${heading} text-base`} style={{ color: INK }}>{open ? `${plural(open, "link")} to add` : "All links handled"}</h3>
          <span className="text-xs text-[#7a838c]">{live} of {t.suggestions.length} confirmed live</span>
        </div>

        {t.suggestions.map((s, i) => {
          const st = statusOf(s);
          const pill = STATUS_PILL[st];
          const anchor = anchorOf(s);
          const place = placement(s, anchor);
          const options = candidates(s);
          const id = `${t.target_url}|${s.source_url}`;
          const written = place.existing ? null : sentenceOf(s);
          const busy = writingOf(s);
          const cut = written ? written.sentence.indexOf(written.anchor) : -1;
          const link = (words: string) => `<a href="${t.target_url}">${words}</a>`;
          const html = written && cut >= 0 ? `${written.sentence.slice(0, cut)}${link(written.anchor)}${written.sentence.slice(cut + written.anchor.length)}` : link(anchor);
          const seen = checkedOf(s);
          const found = seen?.anchor ?? s.live_anchor;
          const note = noteOf(s);
          return (
            <article key={s.source_url} className="flex flex-col gap-3 rounded-xl bg-white px-[18px] py-4" style={{ border: `1px solid ${st === "live" ? "#bfe9e4" : "#ececec"}`, opacity: st === "skipped" ? 0.6 : 1 }}>
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-start gap-3">
                  <span className="flex h-6 w-6 flex-none items-center justify-center rounded-full text-xs font-bold" style={{ background: st === "live" ? TEAL : st === "skipped" ? "#eef0f1" : DARK, color: st === "skipped" ? "#909a9f" : "#fff" }}>
                    {st === "live" ? "✓" : i + 1}
                  </span>
                  <div className="min-w-0">
                    <div className="text-xs text-[#7a838c]">Add a link on</div>
                    <div className="font-bold" style={{ color: INK }}>{s.source_title}</div>
                    <a href={s.source_url} target="_blank" rel="noreferrer" className="break-all text-xs text-[#00857b] hover:underline">{shortPage(s.source_url)}</a>
                  </div>
                </div>
                <span className="flex-none rounded-full px-2.5 py-0.5 text-[11px] font-semibold" style={{ background: pill.background, color: pill.color }}>{pill.label}</span>
              </div>

              {st === "todo" || st === "added" ? (
                <div className="ml-9 flex flex-col gap-2.5">
                  <div className="text-[13px] text-[#4a5560]">{written ? place.instruction.replace("Add a sentence with this link", "Add this sentence") : place.instruction}</div>
                  <div className="flex items-start gap-3 rounded-[10px] bg-[#f8f8f8] px-3.5 py-3">
                    <div className="flex-1 text-sm leading-[1.6]">
                      {place.near ? <div className="mb-1.5 text-[13px] text-[#7a838c]">“{place.near}”</div> : null}
                      {written && cut >= 0 ? written.sentence.slice(0, cut) : place.pre}
                      <span className="rounded px-[3px] py-px font-semibold underline underline-offset-[3px]" style={{ background: "#c6f2ed", color: "#00665f" }}>{written && cut >= 0 ? written.anchor : place.mark}</span>
                      {written && cut >= 0 ? written.sentence.slice(cut + written.anchor.length) : place.post}
                      {!place.existing && s.paragraph ? (
                        <div className="mt-2">
                          <button type="button" onClick={() => onWrite(s)} disabled={busy} className="text-xs font-semibold text-[#00857b] hover:underline disabled:opacity-60">
                            {busy ? "Writing the sentence…" : written ? "Write it again" : "Write the sentence"}
                          </button>
                        </div>
                      ) : null}
                    </div>
                    <button type="button" onClick={() => onCopy(id, html)} className="flex-none rounded-full border border-[#d3d7d9] bg-white px-3 py-[5px] text-xs font-semibold hover:border-[#e6f7f5] hover:bg-[#e6f7f5]" style={{ color: DARK }}>
                      {copied === id ? "Copied ✓" : "Copy HTML"}
                    </button>
                  </div>
                  {options.length > 1 ? (
                    <div className="flex flex-wrap items-center gap-1.5 text-xs text-[#7a838c]">
                      <span>Link text:</span>
                      {options.map((a) => {
                        const on = a === anchor;
                        return (
                          <button key={a} type="button" aria-pressed={on} onClick={() => onChoose(s, a)} className="rounded-full border px-2.5 py-0.5 text-xs font-semibold" style={on ? { background: DARK, borderColor: DARK, color: "#fff" } : { background: "#fff", borderColor: "#e3e6e8", color: "#171a22" }}>
                            {a}
                          </button>
                        );
                      })}
                    </div>
                  ) : null}
                  {showWhy ? (
                    <div className="text-xs text-[#7a838c]">
                      Why this page: {Math.round(s.similarity * 100)}% similar subject{s.source_clicks >= 1 ? `, and it earned ${plural(s.source_clicks, "click")} in 3 months to pass on` : ""}.
                    </div>
                  ) : null}
                </div>
              ) : null}

              <div className="ml-9 flex flex-wrap items-center gap-3">
                {st === "todo" ? (
                  <>
                    <button type="button" onClick={() => onMove(s, "added")} className="rounded-full px-4 py-[7px] text-xs font-semibold text-white hover:bg-[#00a99d]" style={{ background: DARK }}>Mark as added</button>
                    <button type="button" onClick={() => onMove(s, "skipped")} className="text-xs font-semibold text-[#7a838c] hover:underline">Skip</button>
                  </>
                ) : null}
                {st === "added" ? (
                  <>
                    <button type="button" onClick={() => onCheck(s)} className="rounded-full px-4 py-[7px] text-xs font-semibold" style={{ background: "#e9fedc", color: INK }}>Check it’s live</button>
                    <button type="button" onClick={() => onMove(s, "todo")} className="text-xs font-semibold text-[#7a838c] hover:underline">Undo</button>
                  </>
                ) : null}
                {st === "checking" ? (
                  <span className="flex items-center gap-2 text-xs text-[#4a5560]">
                    <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-[#e3e6e8]" style={{ borderTopColor: TEAL }} />
                    Checking the live page…
                  </span>
                ) : null}
                {st === "live" ? <span className="text-xs text-[#00665f]">Found on the live page {when(seen?.at ?? s.checked_at)}{found ? `, linked from “${found}”` : ""}.</span> : null}
                {st === "skipped" ? <button type="button" onClick={() => onMove(s, "todo")} className="text-xs font-semibold text-[#00857b] hover:underline">Restore</button> : null}
                {note ? <span role="alert" className="text-xs font-semibold text-red-700">{note}</span> : null}
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}
