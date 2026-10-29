"use client";

import { useMemo, useState, useTransition } from "react";

import {
  saveConversionDefinitionsAction,
  saveConversionPagesAction,
} from "@/app/(app)/[clientSlug]/settings/conversions/actions";
import { SaveBar, inputClass } from "@/components/ui/form";
import { CONVERSION_TYPES, type ConversionPage, type EventCandidate } from "@/lib/conversions";

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
}: {
  clientId: string;
  slug: string;
  pages: ConversionPage[];
}) {
  const save = useSaving();
  const [rows, setRows] = useState<ConversionPage[]>(pages);

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
    </form>
  );
}
