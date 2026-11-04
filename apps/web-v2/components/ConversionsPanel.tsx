"use client";

import { useMemo, useState, useTransition } from "react";

import {
  loadGa4PagesAction,
  saveCompletionPatternsAction,
  saveConversionDefinitionsAction,
  saveConversionPagesAction,
} from "@/app/(app)/[clientSlug]/settings/conversions/actions";
import { SaveBar, inputClass } from "@/components/ui/form";
import { Spinner } from "@/components/ui/Spinner";
import {
  CONVERSION_TYPES,
  labelFromPath,
  type CompletionPattern,
  type ConversionPage,
  type EventCandidate,
  type Ga4Page,
  type SuggestedPattern,
  type TrackedSummary,
} from "@/lib/conversions";

type Row = { ticked: boolean; name: string; type: string; active: boolean };

function useSaving() {
  const [pending, startTransition] = useTransition();
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return {
    pending,
    saved,
    error,
    dirty: () => setSaved(false),
    run(task: () => Promise<{ ok: true } | { ok: false; error: string }>) {
      setError(null);
      setSaved(false);
      startTransition(async () => {
        const result = await task();
        if (result.ok) setSaved(true);
        else setError(result.error);
      });
    },
  };
}

export function ConversionEvents({
  clientId,
  slug,
  events,
}: {
  clientId: string;
  slug: string;
  events: EventCandidate[];
}) {
  const save = useSaving();
  const [rows, setRows] = useState<Record<string, Row>>(() =>
    Object.fromEntries(
      events.map((e) => [
        e.event_name,
        {
          ticked: e.defined,
          name: e.conversion_name ?? e.event_name,
          type: e.conversion_type ?? "lead",
          active: e.active ?? true,
        },
      ]),
    ),
  );
  const [primary, setPrimary] = useState(events.find((e) => e.is_primary)?.event_name ?? "");
  const [showAutomatic, setShowAutomatic] = useState(false);
  const [query, setQuery] = useState("");

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events
      .filter((e) => (showAutomatic || !e.automatic || rows[e.event_name]?.ticked))
      .filter((e) => !q || e.event_name.toLowerCase().includes(q))
      .sort(
        (a, b) =>
          Number(rows[b.event_name]?.ticked) - Number(rows[a.event_name]?.ticked) ||
          Number(b.suggested) - Number(a.suggested) ||
          b.event_count - a.event_count,
      );
  }, [events, rows, showAutomatic, query]);

  const ticked = events.filter((e) => rows[e.event_name]?.ticked);

  function patch(event: string, change: Partial<Row>) {
    setRows((current) => ({ ...current, [event]: { ...current[event], ...change } }));
    save.dirty();
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save.run(() =>
          saveConversionDefinitionsAction(
            clientId,
            slug,
            ticked.map((e) => ({
              event_name: e.event_name,
              conversion_name: rows[e.event_name].name.trim() || e.event_name,
              conversion_type: rows[e.event_name].type,
              is_primary: primary === e.event_name,
              active: rows[e.event_name].active,
            })),
          ),
        );
      }}
      className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6"
    >
      <h2 className="text-sm font-semibold">Conversions from GA4</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        Tick the GA4 events that count as a conversion for this client. Events GA4 collects on its own
        (page views, scrolls) are hidden unless you show them. The primary one is what the Decision
        Engine falls back to.
      </p>

      <div className="mt-4 flex items-center gap-4">
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={`Search ${events.length} events…`}
          aria-label="Search events"
          className={inputClass}
        />
        <label className="flex shrink-0 items-center gap-2 text-sm">
          <input type="checkbox" checked={showAutomatic} onChange={(e) => setShowAutomatic(e.target.checked)} />
          Show automatic events
        </label>
      </div>

      {events.length === 0 ? (
        <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
          GA4 has not reported any events yet. Connect GA4 and pull its data first.
        </p>
      ) : (
        <ul className="mt-4 divide-y divide-[var(--border)] text-sm">
          {shown.map((event) => {
            const row = rows[event.event_name];
            return (
              <li key={event.event_name} className="grid items-center gap-3 py-2 sm:grid-cols-[auto_1fr_auto]">
                <input
                  type="checkbox"
                  checked={row.ticked}
                  onChange={(e) => {
                    patch(event.event_name, { ticked: e.target.checked });
                    if (!e.target.checked && primary === event.event_name) setPrimary("");
                  }}
                  aria-label={`${event.event_name} counts as a conversion`}
                />
                <div className="min-w-0">
                  <span className="font-medium">{event.event_name}</span>
                  {event.suggested ? (
                    <span className="ml-2 rounded bg-[var(--brand-teal)]/10 px-1.5 py-0.5 text-xs font-semibold text-[var(--brand-teal)]">
                      looks like a lead
                    </span>
                  ) : null}
                  {event.automatic ? (
                    <span className="ml-2 text-xs text-[var(--text-tertiary)]">automatic</span>
                  ) : null}
                  <div className="text-xs text-[var(--text-secondary)]">
                    {event.event_count.toLocaleString()} in the last 90 days · fired on {event.pages} page
                    {event.pages === 1 ? "" : "s"}
                    {event.last_seen ? ` · last seen ${event.last_seen}` : ""}
                  </div>
                </div>
                {row.ticked ? (
                  <div className="flex flex-wrap items-center gap-3 text-xs">
                    <input
                      value={row.name}
                      onChange={(e) => patch(event.event_name, { name: e.target.value })}
                      aria-label={`Name for ${event.event_name}`}
                      className="w-40 rounded-lg border border-[var(--border)] px-2 py-1.5"
                    />
                    <select
                      value={row.type}
                      onChange={(e) => patch(event.event_name, { type: e.target.value })}
                      aria-label={`Type for ${event.event_name}`}
                      className="rounded-lg border border-[var(--border)] px-2 py-1.5"
                    >
                      {CONVERSION_TYPES.map((t) => (
                        <option key={t.value} value={t.value}>
                          {t.label}
                        </option>
                      ))}
                    </select>
                    <label className="flex items-center gap-1.5">
                      <input
                        type="radio"
                        name="primary-conversion"
                        checked={primary === event.event_name}
                        onChange={() => {
                          setPrimary(event.event_name);
                          save.dirty();
                        }}
                      />
                      Primary
                    </label>
                  </div>
                ) : (
                  <span />
                )}
              </li>
            );
          })}
          {shown.length === 0 ? <li className="py-3 text-[var(--text-tertiary)]">No event matches.</li> : null}
        </ul>
      )}
      <SaveBar pending={save.pending} saved={save.saved} error={save.error} />
    </form>
  );
}

export function ConversionPages({
  clientId,
  slug,
  pages,
  events,
  patterns: initialPatterns,
}: {
  clientId: string;
  slug: string;
  pages: ConversionPage[];
  events: EventCandidate[];
  patterns: CompletionPattern[];
}) {
  const save = useSaving();
  const [rows, setRows] = useState<ConversionPage[]>(pages);
  const [patterns, setPatterns] = useState<CompletionPattern[]>(initialPatterns);

  function addPage(page: Ga4Page) {
    setRows((current) =>
      current.some((r) => r.normalized_url === page.url)
        ? current
        : [...current, { normalized_url: page.url, label: labelFromPath(page.path), stage: null, is_primary: false }],
    );
    save.dirty();
  }

  function patch(index: number, change: Partial<ConversionPage>) {
    setRows((current) =>
      current.map((row, i) => {
        if (i === index) return { ...row, ...change };
        // Only one page is the primary offer.
        return change.is_primary ? { ...row, is_primary: false } : row;
      }),
    );
    save.dirty();
  }

  return (
    <div className="space-y-6">
    <form
      onSubmit={(event) => {
        event.preventDefault();
        save.run(() =>
          saveConversionPagesAction(
            clientId,
            slug,
            rows
              .filter((r) => r.normalized_url.trim() && r.label.trim())
              .map((r) => ({
                normalized_url: r.normalized_url.trim(),
                label: r.label.trim(),
                stage: r.stage,
                is_primary: r.is_primary,
              })),
          ),
        );
      }}
      className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6"
    >
      <h2 className="text-sm font-semibold">Conversion pages</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        The pages a visitor lands on to convert: the contact page, a quote form, a booking page. The
        engine sends internal links and calls to action there, and a page you declare beats its guess
        from the address.
      </p>

      <ul className="mt-4 space-y-2">
        {rows.map((row, index) => (
          <li key={index} className="grid gap-2 sm:grid-cols-[2fr_1fr_auto_auto]">
            <input
              value={row.normalized_url}
              onChange={(e) => patch(index, { normalized_url: e.target.value })}
              placeholder="https://example.com/contact-us"
              aria-label="Page address"
              className={inputClass}
            />
            <input
              value={row.label}
              onChange={(e) => patch(index, { label: e.target.value })}
              placeholder="Contact"
              aria-label="Label"
              className={inputClass}
            />
            <label className="flex items-center gap-1.5 text-sm">
              <input
                type="radio"
                name="primary-page"
                checked={row.is_primary}
                onChange={() => patch(index, { is_primary: true })}
              />
              Primary
            </label>
            <button
              type="button"
              onClick={() => {
                setRows((current) => current.filter((_, i) => i !== index));
                save.dirty();
              }}
              className="text-xs font-semibold text-red-700 hover:underline"
            >
              Remove
            </button>
          </li>
        ))}
        {rows.length === 0 ? <li className="text-sm text-[var(--text-tertiary)]">No conversion page yet.</li> : null}
      </ul>
      <button
        type="button"
        onClick={() => setRows((current) => [...current, { normalized_url: "", label: "", stage: null, is_primary: false }])}
        className="mt-3 text-sm font-semibold text-[var(--brand-teal)] hover:underline"
      >
        + Add a page
      </button>
      <SaveBar pending={save.pending} saved={save.saved} error={save.error} />
      <Ga4PagesPanel
        clientId={clientId}
        events={events}
        onAdd={addPage}
        added={new Set(rows.map((r) => r.normalized_url))}
        tracked={patterns.map((p) => p.pattern)}
        onTrack={async (pattern) => {
          const next = [...patterns, { pattern, label: null }];
          const result = await saveCompletionPatternsAction(clientId, slug, next);
          if (result.ok) setPatterns(next);
          return result;
        }}
      />
    </form>
    <CompletionCard clientId={clientId} slug={slug} patterns={patterns} onChange={setPatterns} />
    </div>
  );
}

/** The pages GA4 says each chosen event fired on, so a conversion page can be picked, not remembered. */
function Ga4PagesPanel({
  clientId,
  events,
  onAdd,
  added,
  tracked,
  onTrack,
}: {
  clientId: string;
  events: EventCandidate[];
  onAdd: (page: Ga4Page) => void;
  added: Set<string>;
  tracked: string[];
  onTrack: (pattern: string) => Promise<{ ok: true } | { ok: false; error: string }>;
}) {
  const choices = events.filter((e) => !e.automatic && e.event_count > 0);
  const initial = (events.some((e) => e.defined) ? events.filter((e) => e.defined) : events.filter((e) => e.suggested)).map(
    (e) => e.event_name,
  );
  const [chosen, setChosen] = useState<string[]>(initial);
  const [days, setDays] = useState(90);
  const [pages, setPages] = useState<Ga4Page[] | null>(null);
  const [suggested, setSuggested] = useState<SuggestedPattern[]>([]);
  const [trackedSummary, setTrackedSummary] = useState<TrackedSummary[]>([]);
  const [notShown, setNotShown] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function load() {
    setError(null);
    startTransition(async () => {
      const result = await loadGa4PagesAction(clientId, chosen, days);
      if (result.ok) {
        setPages(result.pages);
        setSuggested(result.suggested);
        setTrackedSummary(result.tracked);
        setNotShown(result.notShown);
      } else setError(result.error);
    });
  }

  const untrackedSuggestions = suggested.filter((s) => !tracked.includes(s.pattern));
  // The API folds pages that match a pattern away; only a pattern tracked after loading needs hiding here.
  const visible = pages?.filter((p) => !tracked.some((t) => p.path.toLowerCase().includes(t))) ?? [];

  return (
    <div className="mt-8 border-t border-[var(--border)] pt-6">
      <h3 className="text-sm font-semibold">What GA4 sees</h3>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        The pages where a conversion event actually fired, straight from GA4. A contact page or a
        thank-you page shows up near the top. Choose the events to look at, then add a page to the list
        above.
      </p>

      <div className="mt-3 flex flex-wrap gap-2">
        {choices.map((event) => {
          const on = chosen.includes(event.event_name);
          return (
            <button
              key={event.event_name}
              type="button"
              aria-pressed={on}
              onClick={() =>
                setChosen((current) =>
                  on ? current.filter((n) => n !== event.event_name) : [...current, event.event_name],
                )
              }
              className={`rounded-full border px-3 py-1 text-xs font-semibold ${
                on
                  ? "border-[var(--brand-teal)] bg-[var(--brand-teal)] text-white"
                  : "border-[var(--border)] hover:border-[var(--brand-teal)]"
              }`}
            >
              {event.event_name}
            </button>
          );
        })}
        {choices.length === 0 ? (
          <span className="text-sm text-[var(--text-tertiary)]">GA4 has no non-automatic events yet.</span>
        ) : null}
      </div>

      <div className="mt-3 flex items-center gap-3">
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          aria-label="Time frame"
          className="rounded-lg border border-[var(--border)] px-2 py-1.5 text-sm"
        >
          <option value={30}>Last 30 days</option>
          <option value={90}>Last 90 days</option>
          <option value={365}>Last 12 months</option>
        </select>
        <button
          type="button"
          disabled={pending || chosen.length === 0}
          onClick={load}
          className="rounded-lg bg-[var(--brand-dark)] px-4 py-1.5 text-sm font-semibold text-white disabled:opacity-50"
        >
          {pending ? <><Spinner />Asking GA4…</> : "Show pages"}
        </button>
      </div>
      {error ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}

      {untrackedSuggestions.map((s) => (
        <div
          key={s.pattern}
          className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--brand-teal)]/10 p-3 text-sm"
        >
          <span>
            <strong>{s.pattern}</strong>: {s.total.toLocaleString()} conversions across {s.pages.toLocaleString()}{" "}
            different page addresses. Track them as one?
          </span>
          <button
            type="button"
            onClick={async () => {
              const result = await onTrack(s.pattern);
              if (!result.ok) setError(result.error);
            }}
            className="rounded-lg bg-[var(--brand-teal)] px-3 py-1.5 text-xs font-semibold text-white"
          >
            Track {s.pattern}
          </button>
        </div>
      ))}
      {trackedSummary.map((t) => (
        <p key={t.pattern} className="mt-3 text-xs text-[var(--text-secondary)]">
          <strong>{t.pattern}</strong> is tracked: {t.total.toLocaleString()} conversions across{" "}
          {t.pages.toLocaleString()} page addresses, folded out of the list below.
        </p>
      ))}

      {pages ? (
        visible.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">GA4 saw none of those events in that time.</p>
        ) : (
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
              <tr>
                <th className="py-2 font-medium">Page</th>
                <th className="px-3 py-2 text-right font-medium">Events</th>
                <th className="px-3 py-2 font-medium">By event</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {visible.slice(0, 40).map((page) => (
                <tr key={page.url} className="border-t border-[var(--border)]">
                  <td className="max-w-[18rem] truncate py-2" title={page.url}>
                    {page.path}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{page.total.toLocaleString()}</td>
                  <td className="px-3 py-2 text-xs text-[var(--text-secondary)]">
                    {Object.entries(page.events)
                      .map(([name, count]) => `${name} ${count.toLocaleString()}`)
                      .join(" · ")}
                  </td>
                  <td className="py-2 text-right">
                    {page.path === "(not set)" ? null : added.has(page.url) || page.declared ? (
                      <span className="text-xs text-[var(--text-tertiary)]">Added</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => onAdd(page)}
                        className="text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                      >
                        Add
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )
      ) : null}
      {visible.length > 40 || notShown > 0 ? (
        <p className="mt-2 text-xs text-[var(--text-tertiary)]">
          Showing the busiest 40 of {(visible.length + notShown).toLocaleString()}.
        </p>
      ) : null}
      {visible.some((p) => p.path === "(not set)") ? (
        <p className="mt-2 text-xs text-[var(--text-tertiary)]">
          &ldquo;(not set)&rdquo; means GA4 recorded the event with no page, usually a tracking gap rather than a
          real page.
        </p>
      ) : null}
    </div>
  );
}

/** Address patterns that mean "finished": counted, never linked to. */
function CompletionCard({
  clientId,
  slug,
  patterns,
  onChange,
}: {
  clientId: string;
  slug: string;
  patterns: CompletionPattern[];
  onChange: (next: CompletionPattern[]) => void;
}) {
  const save = useSaving();
  const [draft, setDraft] = useState("");

  function persist(next: CompletionPattern[]) {
    save.run(async () => {
      const result = await saveCompletionPatternsAction(clientId, slug, next);
      if (result.ok) onChange(next);
      return result;
    });
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <h2 className="text-sm font-semibold">Thank-you pages</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        A finished order or form often lands on an address that is different every time, such as
        <code className="mx-1">/checkouts/cn/&lt;order code&gt;/en-us/thank-you</code>. Track the part that
        never changes, like <code className="mx-1">/thank-you</code>, and every one of them counts. These are
        for measuring conversions only: the engine never sends readers to them.
      </p>

      <ul className="mt-4 divide-y divide-[var(--border)] text-sm">
        {patterns.map((p) => (
          <li key={p.pattern} className="flex items-center justify-between py-2">
            <span className="font-medium">
              {p.pattern}
              {p.label ? <span className="font-normal text-[var(--text-secondary)]"> · {p.label}</span> : null}
            </span>
            <button
              type="button"
              disabled={save.pending}
              onClick={() => persist(patterns.filter((x) => x.pattern !== p.pattern))}
              className="text-xs font-semibold text-red-700 hover:underline disabled:opacity-50"
            >
              Remove
            </button>
          </li>
        ))}
        {patterns.length === 0 ? <li className="py-2 text-[var(--text-tertiary)]">Nothing tracked yet.</li> : null}
      </ul>

      <div className="mt-3 flex gap-3">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              document.getElementById("add-completion")?.click();
            }
          }}
          placeholder="/thank-you"
          aria-label="Page address pattern"
          className={inputClass}
        />
        <button
          id="add-completion"
          type="button"
          disabled={save.pending || !draft.trim()}
          onClick={() => {
            const text = draft.trim().toLowerCase();
            const pattern = text.startsWith("/") ? text : `/${text}`;
            if (!patterns.some((p) => p.pattern === pattern)) persist([...patterns, { pattern, label: null }]);
            setDraft("");
          }}
          className="shrink-0 rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Track
        </button>
      </div>
      {save.saved ? <p className="mt-2 text-sm text-[var(--text-secondary)]">Saved.</p> : null}
      {save.error ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {save.error}
        </p>
      ) : null}
    </div>
  );
}
