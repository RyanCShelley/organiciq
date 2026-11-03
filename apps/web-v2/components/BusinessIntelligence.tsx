"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { addChangeAction, removeChangeAction } from "@/app/(app)/[clientSlug]/bi/actions";
import { Spinner } from "@/components/ui/Spinner";
import type { Client } from "@/lib/api";
import { presets, type Bi, type BiChange, type BiKeyword } from "@/lib/bi";

const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString());
const pct = (n: number | null | undefined) => (n == null ? "–" : `${n.toFixed(1)}%`);
const shortPage = (url: string) => url.replace(/^https?:\/\/[^/]+/, "") || "/";
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
const TYPE_LABEL: Record<string, string> = {
  growth_action: "Growth action",
  content_published: "Content published",
  content_updated: "Content updated",
  technical_change: "Technical change",
  website_change: "Website change",
  conversion_change: "Conversion change",
  campaign_change: "Campaign change",
  algorithm_event: "Algorithm update",
  manual_note: "Note",
};

/** Time on site, as a person says it. */
function duration(seconds: number | null | undefined) {
  if (seconds == null) return "–";
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

function Delta({ now, before }: { now: number; before: number }) {
  if (!before) return <span className="text-xs text-[var(--text-tertiary)]">no earlier figure</span>;
  const change = ((now - before) / before) * 100;
  const flat = Math.abs(change) < 1;
  return (
    <span className={`text-xs font-semibold ${flat ? "text-[var(--text-secondary)]" : change > 0 ? "text-green-700" : "text-red-700"}`}>
      {flat ? "flat" : `${change > 0 ? "▲" : "▼"} ${Math.abs(change).toFixed(0)}%`}
    </span>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4">
      <div className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-2xl font-bold tabular-nums">{value}</div>
      {note ? <div className="mt-1 text-xs">{note}</div> : null}
    </div>
  );
}

const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-[var(--text-tertiary)]";
const td = "px-3 py-2 tabular-nums";

function KeywordRow({ k }: { k: BiKeyword }) {
  const style = k.state === "up" || k.state === "new" ? "text-green-700" : k.state === "down" || k.state === "lost" ? "text-red-700" : "text-[var(--text-secondary)]";
  const text =
    k.state === "new" ? "now ranking" : k.state === "lost" ? "dropped out" : k.change == null ? "–" : k.state === "steady" ? "steady" : `${k.change > 0 ? "▲" : "▼"} ${Math.abs(k.change)}`;
  return (
    <tr className="border-t border-[var(--border)]">
      <td className="px-3 py-2 font-medium">{k.keyword}</td>
      <td className={td}>{k.start ?? "–"}</td>
      <td className={td}>{k.end ?? "–"}</td>
      <td className={`${td} font-semibold ${style}`}>{text}</td>
      <td className={td}>{num(k.volume)}</td>
    </tr>
  );
}

function ChangeLog({ clientId, slug, from, to, changes }: { clientId: string; slug: string; from: string; to: string; changes: BiChange[] }) {
  const router = useRouter();
  const [date, setDate] = useState(to);
  const [text, setText] = useState("");
  const [page, setPage] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();
  const add = () =>
    start(async () => {
      setError(null);
      const r = await addChangeAction(clientId, slug, date, text, page);
      if (r.ok) {
        setText("");
        setPage("");
        router.refresh();
      } else setError(r.error);
    });
  const remove = (id: string) =>
    start(async () => {
      const r = await removeChangeAction(clientId, slug, id);
      if (r.ok) router.refresh();
      else setError(r.error);
    });
  const input = "rounded-lg border border-[var(--border)] bg-white px-3 py-2 text-sm";
  return (
    <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5">
      <h2 className="font-semibold">Change log</h2>
      <p className="mt-1 text-xs text-[var(--text-tertiary)]">
        What changed on the site or in the work, so a movement in the numbers above can be tied to something. Shipping a task adds its entry here; add anything else by hand.
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-xs font-semibold">
          Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`mt-1 block ${input}`} />
        </label>
        <label className="min-w-[16rem] flex-1 text-xs font-semibold">
          What changed
          <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Moved the SPF collection to a new template" className={`mt-1 block w-full ${input}`} />
        </label>
        <label className="min-w-[10rem] text-xs font-semibold">
          Page (optional)
          <input value={page} onChange={(e) => setPage(e.target.value)} placeholder="/collections/spf" className={`mt-1 block w-full ${input}`} />
        </label>
        <button type="button" onClick={add} disabled={pending || text.trim().length < 3 || !date} className="rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50">
          {pending ? <><Spinner />Saving…</> : "Add"}
        </button>
      </div>
      {error ? <p role="alert" className="mt-2 text-sm font-semibold text-red-700">{error}</p> : null}
      {changes.length === 0 ? (
        <p className="mt-4 text-sm text-[var(--text-secondary)]">Nothing logged between {day(from)} and {day(to)}.</p>
      ) : (
        <ul className="mt-4 divide-y divide-[var(--border)] text-sm">
          {changes.map((c) => (
            <li key={c.id} className="flex flex-wrap items-start gap-3 py-2">
              <span className="w-28 shrink-0 text-xs tabular-nums text-[var(--text-secondary)]">{day(c.date)}</span>
              <span className="w-36 shrink-0 text-xs font-semibold">{TYPE_LABEL[c.type] ?? c.type}</span>
              <span className="min-w-0 flex-1">
                {c.description}
                {c.page ? <span className="ml-2 text-xs text-[var(--text-tertiary)]">{shortPage(c.page)}</span> : null}
              </span>
              {!c.from_task ? (
                <button type="button" onClick={() => remove(c.id)} disabled={pending} className="text-xs font-semibold text-red-700 underline disabled:opacity-50">
                  Remove
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function BusinessIntelligence({ client, from, to, channel, data, error }: { client: Client; from: string; to: string; channel: string; data: Bi | null; error: string | null }) {
  const router = useRouter();
  const [custom, setCustom] = useState({ from, to });
  const go = (f: string, t: string, c = channel) => {
    const q = new URLSearchParams({ from: f, to: t });
    if (c) q.set("channel", c);
    router.push(`/${client.slug}/bi?${q}`);
  };
  const ranges = presets();
  const active = ranges.find((r) => r.from === from && r.to === to)?.key ?? "custom";

  const sessions = data?.channels.reduce((n, c) => n + c.sessions, 0) ?? 0;
  const before = data?.channels.reduce((n, c) => n + c.sessions_before, 0) ?? 0;
  const conversions = data?.channels.reduce((n, c) => n + c.conversions, 0) ?? 0;
  const conversionsBefore = data?.channels.reduce((n, c) => n + c.conversions_before, 0) ?? 0;
  const timed = data?.channels.filter((c) => c.avg_seconds != null) ?? [];
  const timedSessions = timed.reduce((n, c) => n + c.sessions, 0);
  const avgSeconds = timedSessions > 0 ? timed.reduce((n, c) => n + (c.avg_seconds ?? 0) * c.sessions, 0) / timedSessions : null;
  const noEvents = data != null && data.key_events.length === 0;

  return (
    <section className="max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Business Intelligence</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          Behind the monthly review: where visits and conversions come from, which pages carry them, and how tracked keywords moved. Compared with the same number of days before.
        </p>
      </header>

      <div className="flex flex-wrap items-end gap-2 text-sm">
        {ranges.map((r) => (
          <button
            key={r.key}
            type="button"
            onClick={() => go(r.from, r.to)}
            className={`rounded-lg border px-3 py-1.5 font-semibold ${active === r.key ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white" : "border-[var(--border)] bg-white"}`}
          >
            {r.label}
          </button>
        ))}
        <label className="text-xs font-semibold">
          From
          <input type="date" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" />
        </label>
        <label className="text-xs font-semibold">
          To
          <input type="date" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} className="mt-1 block rounded-lg border border-[var(--border)] bg-white px-2 py-1.5 text-sm" />
        </label>
        <button type="button" onClick={() => go(custom.from, custom.to)} disabled={!custom.from || !custom.to || custom.to < custom.from} className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 font-semibold disabled:opacity-50">
          Apply
        </button>
      </div>

      {error ? <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-800">{error}</p> : null}

      {data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Visits" value={num(sessions)} note={<Delta now={sessions} before={before} />} />
            <Stat label="Key actions" value={noEvents ? "–" : num(conversions)} note={noEvents ? <span className="text-[var(--text-tertiary)]">none chosen yet</span> : <Delta now={conversions} before={conversionsBefore} />} />
            <Stat label="Conversion rate" value={noEvents ? "–" : pct(sessions > 0 ? (conversions / sessions) * 100 : null)} />
            <Stat label="Time on site" value={duration(avgSeconds)} note={!data.has_engagement_time ? <span className="text-[var(--text-tertiary)]">pull Google Analytics again to fill this</span> : <span className="text-[var(--text-tertiary)]">engaged time per visit</span>} />
          </div>

          {noEvents ? (
            <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
              No key actions are chosen for this client, so conversions show as a dash. Choose them in{" "}
              <Link href={`/${client.slug}/settings/conversions`} className="font-semibold underline">Settings → Conversions</Link>.
            </p>
          ) : (
            <p className="text-xs text-[var(--text-tertiary)]">Key actions counted: {data.key_events.map((e) => e.name).join(", ")}.</p>
          )}

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            <h2 className="px-5 pt-4 font-semibold">Channels</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">Choose a channel to see its landing pages below.</p>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr>
                    <th className={th}>Channel</th>
                    <th className={th}>Visits</th>
                    <th className={th}>Engaged</th>
                    <th className={th}>Time</th>
                    <th className={th}>Key actions</th>
                    <th className={th}>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.channels.map((c) => (
                    <tr key={c.channel} className={`border-t border-[var(--border)] ${channel === c.channel ? "bg-[var(--bg)]" : ""}`}>
                      <td className="px-3 py-2">
                        <button type="button" onClick={() => go(from, to, channel === c.channel ? "" : c.channel)} className="font-semibold underline-offset-2 hover:underline">
                          {c.label}
                        </button>
                      </td>
                      <td className={td}>
                        {num(c.sessions)} <Delta now={c.sessions} before={c.sessions_before} />
                      </td>
                      <td className={td}>{pct(c.engagement_rate)}</td>
                      <td className={td}>{duration(c.avg_seconds)}</td>
                      <td className={td}>{noEvents ? "–" : num(c.conversions)}</td>
                      <td className={td}>{noEvents ? "–" : pct(c.conversion_rate)}</td>
                    </tr>
                  ))}
                  {data.channels.length === 0 ? (
                    <tr><td colSpan={6} className="px-5 py-4 text-[var(--text-secondary)]">No Google Analytics data between {day(from)} and {day(to)}.</td></tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            <h2 className="px-5 pt-4 font-semibold">
              Landing pages{channel ? `: ${data.channels.find((c) => c.channel === channel)?.label ?? channel}` : ""}
            </h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">The 25 busiest pages people arrive on.{channel ? " Showing one channel." : ""}</p>
            <div className="overflow-x-auto">
              <table className="mt-2 w-full text-sm">
                <thead>
                  <tr>
                    <th className={th}>Page</th>
                    <th className={th}>Visits</th>
                    <th className={th}>Engaged</th>
                    <th className={th}>Time</th>
                    <th className={th}>Key actions</th>
                    <th className={th}>Rate</th>
                  </tr>
                </thead>
                <tbody>
                  {data.pages.map((p) => (
                    <tr key={p.url} className="border-t border-[var(--border)]">
                      <td className="max-w-md break-all px-3 py-2 font-medium" title={p.url}>{shortPage(p.url)}</td>
                      <td className={td}>{num(p.sessions)}</td>
                      <td className={td}>{pct(p.engagement_rate)}</td>
                      <td className={td}>{duration(p.avg_seconds)}</td>
                      <td className={td}>{noEvents ? "–" : num(p.conversions)}</td>
                      <td className={td}>{noEvents ? "–" : pct(p.conversion_rate)}</td>
                    </tr>
                  ))}
                  {data.pages.length === 0 ? <tr><td colSpan={6} className="px-5 py-4 text-[var(--text-secondary)]">No pages for this range.</td></tr> : null}
                </tbody>
              </table>
            </div>
          </section>

          <section className="rounded-xl border border-[var(--border)] bg-[var(--surface)]">
            <h2 className="px-5 pt-4 font-semibold">Tracked keywords: start of the range against the end</h2>
            <p className="px-5 text-xs text-[var(--text-tertiary)]">
              {data.keywords.from && data.keywords.to
                ? `Positions on ${day(data.keywords.from)} and ${day(data.keywords.to)}, the first and last days the rank tracker checked in this range. A dash means not ranking.`
                : "The rank tracker has no check inside this range."}
            </p>
            {data.keywords.keywords.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="mt-2 w-full text-sm">
                  <thead>
                    <tr>
                      <th className={th}>Keyword</th>
                      <th className={th}>Start</th>
                      <th className={th}>End</th>
                      <th className={th}>Move</th>
                      <th className={th}>Searches / month</th>
                    </tr>
                  </thead>
                  <tbody>{data.keywords.keywords.map((k) => <KeywordRow key={k.keyword} k={k} />)}</tbody>
                </table>
              </div>
            ) : null}
          </section>

          <ChangeLog clientId={client.id} slug={client.slug} from={from} to={to} changes={data.changes} />
        </>
      ) : null}
    </section>
  );
}
