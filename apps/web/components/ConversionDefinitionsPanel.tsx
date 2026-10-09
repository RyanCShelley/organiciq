"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import type { ConversionDefinition } from "@/lib/api";

type Candidate = {
  event_name: string;
  event_count: number;
  pages: number;
  last_seen: string | null;
  automatic: boolean;
  suggested: boolean;
  defined: boolean;
  conversion_name: string;
  conversion_type: string;
  is_primary: boolean;
  active: boolean;
};

type Row = {
  ticked: boolean;
  conversion_name: string;
  conversion_type: string;
};

function formatDay(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("en-US", { day: "numeric", month: "short", timeZone: "UTC" });
}

/**
 * Which of this client's GA4 events count as a lead.
 *
 * Twenty of twenty-four clients have none of these set, which blocks the
 * whole lead branch for them. The events have been in the warehouse the
 * whole time; what stood here asked for one at a time — type the event
 * name, type a label, choose a type, submit — which is why nobody did it.
 *
 * So it is a list of the client's own events with a tick against each, and
 * one save. The engine still reads nothing but what is ticked: a suggestion
 * is a pattern match on a name somebody else chose, and `Conversion` may be
 * a real lead or a default left switched on. Only the person who knows the
 * client can say.
 */
export function ConversionDefinitionsPanel({
  clientId,
  conversions,
}: {
  clientId: string;
  conversions: ConversionDefinition[];
}) {
  const router = useRouter();
  const [candidates, setCandidates] = useState<Candidate[] | null>(null);
  const [rows, setRows] = useState<Record<string, Row>>({});
  const [primary, setPrimary] = useState<string | null>(null);
  const [showAutomatic, setShowAutomatic] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const res = await fetch(
        `/api/proxy/conversion-definitions/ga4-events?clientId=${encodeURIComponent(clientId)}`,
      );
      if (!res.ok || cancelled) return;
      const data = (await res.json()) as Candidate[];
      if (cancelled) return;
      setCandidates(data);
      // Ticked means already defined. A suggestion is highlighted, never
      // pre-ticked: pre-ticking a guess and offering a save button makes
      // the guess the decision.
      setRows(
        Object.fromEntries(
          data.map((c) => [
            c.event_name,
            {
              ticked: c.defined,
              conversion_name: c.conversion_name,
              conversion_type: c.conversion_type,
            },
          ]),
        ),
      );
      setPrimary(data.find((c) => c.defined && c.is_primary)?.event_name ?? null);
    })();
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const [shown, automatic] = useMemo(() => {
    const all = candidates ?? [];
    return [all.filter((c) => !c.automatic), all.filter((c) => c.automatic)];
  }, [candidates]);

  const tickedCount = Object.values(rows).filter((r) => r.ticked).length;

  function setRow(name: string, patch: Partial<Row>) {
    setSaved(false);
    setRows((prev) => ({ ...prev, [name]: { ...prev[name], ...patch } }));
  }

  async function save() {
    setSaving(true);
    setError(null);
    const definitions = Object.entries(rows)
      .filter(([, r]) => r.ticked)
      .map(([event_name, r]) => ({
        event_name,
        conversion_name: r.conversion_name.trim() || event_name,
        conversion_type: r.conversion_type,
        is_primary: event_name === primary,
        active: true,
      }));
    const res = await fetch("/api/proxy/conversion-definitions", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ clientId, definitions }),
    });
    setSaving(false);
    if (!res.ok) {
      setError((await res.text()) || "Could not save");
      return;
    }
    setSaved(true);
    router.refresh();
  }

  function renderRow(c: Candidate) {
    const row = rows[c.event_name];
    if (!row) return null;
    return (
      <div
        key={c.event_name}
        className={`grid gap-x-4 gap-y-2 border-t border-[var(--border)] px-4 py-3 sm:grid-cols-[auto_minmax(0,1.3fr)_auto_minmax(0,1fr)_auto] sm:items-center ${
          row.ticked ? "bg-[var(--surface-muted)]" : ""
        }`}
      >
        <label className="flex min-h-[44px] items-center gap-3 sm:min-h-0">
          <input
            type="checkbox"
            checked={row.ticked}
            onChange={(e) => setRow(c.event_name, { ticked: e.target.checked })}
            className="h-4 w-4"
            aria-label={`Count ${c.event_name} as a conversion`}
          />
          <span className="font-[family-name:var(--font-mono)] text-[12.5px] break-all">
            {c.event_name}
          </span>
        </label>

        <span className="text-[12px] text-[var(--text-tertiary)]">
          {c.event_count.toLocaleString()} in 90 days ·{" "}
          {/* The sharpest column here. A lead fires on a handful of pages;
              page_view fires on all of them. */}
          {c.pages.toLocaleString()} {c.pages === 1 ? "page" : "pages"} · last{" "}
          {formatDay(c.last_seen)}
        </span>

        <span className="text-[11px]">
          {c.suggested ? (
            <span className="rounded-full bg-[#E5F4EC] px-2 py-0.5 font-semibold text-[#15784F]">
              Looks like a lead
            </span>
          ) : null}
        </span>

        {row.ticked ? (
          <input
            value={row.conversion_name}
            onChange={(e) => setRow(c.event_name, { conversion_name: e.target.value })}
            aria-label={`Name for ${c.event_name}`}
            className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-[13px]"
          />
        ) : (
          <span />
        )}

        {row.ticked ? (
          <div className="flex items-center gap-3 text-[12px]">
            <select
              value={row.conversion_type}
              onChange={(e) => setRow(c.event_name, { conversion_type: e.target.value })}
              aria-label={`Type for ${c.event_name}`}
              className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2"
            >
              <option value="lead">Lead</option>
              <option value="engagement">Engagement</option>
              <option value="ecommerce">Ecommerce</option>
            </select>
            <label className="flex items-center gap-1.5 whitespace-nowrap">
              <input
                type="radio"
                name="primary-conversion"
                checked={primary === c.event_name}
                onChange={() => {
                  setSaved(false);
                  setPrimary(c.event_name);
                }}
              />
              Primary
            </label>
          </div>
        ) : (
          <span />
        )}
      </div>
    );
  }

  if (candidates === null) {
    return (
      <p className="text-[13px] text-[var(--text-tertiary)]">Reading this client&rsquo;s events…</p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="rounded-[var(--radius-lg,14px)] border border-[var(--border)] bg-[var(--surface)]">
        <div className="flex flex-wrap items-baseline justify-between gap-3 px-4 pb-3 pt-4">
          <div>
            <h3 className="text-[15px] font-semibold text-[var(--text-primary)]">
              Which events are conversions?
            </h3>
            <p className="mt-1 max-w-[80ch] text-[13px] leading-relaxed text-[var(--text-secondary)]">
              Everything this client&rsquo;s GA4 reports, as it reports it. Tick what counts.
              Nothing is ticked for you — &ldquo;looks like a lead&rdquo; is a guess about a
              name somebody else chose, and the engine reads only what you confirm.
            </p>
          </div>
          <span className="text-[12.5px] text-[var(--text-tertiary)]">
            {tickedCount} ticked
          </span>
        </div>

        {shown.length === 0 ? (
          <p className="border-t border-[var(--border)] px-4 py-6 text-[13px] text-[var(--text-secondary)]">
            No events in the last 90 days. Check the GA4 connection before setting conversions.
          </p>
        ) : (
          shown.map(renderRow)
        )}

        {automatic.length > 0 ? (
          <details
            open={showAutomatic}
            onToggle={(e) => setShowAutomatic((e.target as HTMLDetailsElement).open)}
            className="border-t border-[var(--border)]"
          >
            {/* GA4 collects these without anyone asking, so none of them is a
                conversion — but they are the bulk of the list, and hiding
                them outright would be a claim rather than a default. */}
            <summary className="flex min-h-[44px] cursor-pointer items-center px-4 text-[13px] font-semibold text-[var(--brand-teal-deep)]">
              {automatic.length} events GA4 collects on its own
            </summary>
            {automatic.map(renderRow)}
          </details>
        ) : null}
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={save} disabled={saving}>
          {saving ? "Saving…" : "Save conversions"}
        </Button>
        {saved ? (
          <span role="status" className="text-[13px] font-semibold text-[var(--brand-teal-deep)]">
            Saved. The lead branch can run for this client now.
          </span>
        ) : null}
        {conversions.length === 0 && tickedCount === 0 ? (
          <span className="text-[13px] text-[var(--text-tertiary)]">
            Until one is set, every lead rule is blocked for this client.
          </span>
        ) : null}
      </div>
    </div>
  );
}
