"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import type { ConversionDefinition } from "@/lib/api";

type Ga4EventOption = {
  event_name: string;
  event_count: number;
};

export function ConversionDefinitionsPanel({
  clientId,
  conversions,
}: {
  clientId: string;
  conversions: ConversionDefinition[];
}) {
  const router = useRouter();
  const [events, setEvents] = useState<Ga4EventOption[]>([]);
  const [eventName, setEventName] = useState("");
  const [conversionName, setConversionName] = useState("");
  const [conversionType, setConversionType] = useState("lead");
  const [isPrimary, setIsPrimary] = useState(false);
  const [active, setActive] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function loadEvents() {
      const res = await fetch(
        `/api/proxy/conversion-definitions/ga4-events?clientId=${encodeURIComponent(clientId)}`,
      );
      if (!res.ok || cancelled) return;
      const data = (await res.json()) as Ga4EventOption[];
      if (!cancelled) setEvents(data);
    }
    void loadEvents();
    return () => {
      cancelled = true;
    };
  }, [clientId]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    setMessage(null);

    const res = await fetch("/api/proxy/conversion-definitions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        clientId,
        event_name: eventName.trim(),
        conversion_name: conversionName.trim(),
        conversion_type: conversionType,
        is_primary: isPrimary,
        active,
      }),
    });

    const text = await res.text();
    setPending(false);
    if (!res.ok) {
      setMessage(text || "Failed to add conversion");
      return;
    }

    setMessage("Conversion added");
    setEventName("");
    setConversionName("");
    setIsPrimary(false);
    setActive(true);
    router.refresh();
  }

  return (
    <div className="space-y-6">
      <form
        onSubmit={onSubmit}
        className="rounded-xl border border-[var(--border)] bg-[var(--card)] p-4"
      >
        <h3 className="text-sm font-medium">Add conversion definition</h3>
        <p className="mt-1 text-xs text-[var(--muted)]">
          Map a GA4 event name to a lead (or other) conversion for this client only.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            GA4 event name
            <input
              list="ga4-event-options"
              required
              value={eventName}
              onChange={(e) => setEventName(e.target.value)}
              className="rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
              placeholder="generate_lead"
            />
            <datalist id="ga4-event-options">
              {events.map((event) => (
                <option
                  key={event.event_name}
                  value={event.event_name}
                  label={`${event.event_count} events`}
                />
              ))}
            </datalist>
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            Display name
            <input
              required
              value={conversionName}
              onChange={(e) => setConversionName(e.target.value)}
              className="rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
              placeholder="Lead Form Submission"
            />
          </label>
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            Type
            <select
              value={conversionType}
              onChange={(e) => setConversionType(e.target.value)}
              className="rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
            >
              <option value="lead">Lead</option>
              <option value="secondary">Secondary</option>
            </select>
          </label>
          <div className="flex flex-wrap items-end gap-4 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={isPrimary}
                onChange={(e) => setIsPrimary(e.target.checked)}
              />
              Primary
            </label>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
              Active
            </label>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={pending}
            className="rounded-lg bg-[var(--accent)] px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {pending ? "Saving…" : "Add conversion"}
          </button>
          {message ? <p className="text-sm text-[var(--muted)]">{message}</p> : null}
        </div>
        {events.length > 0 ? (
          <p className="mt-3 text-xs text-[var(--muted)]">
            Suggestions from synced GA4 facts:{" "}
            {events
              .slice(0, 5)
              .map((event) => event.event_name)
              .join(", ")}
            {events.length > 5 ? "…" : ""}
          </p>
        ) : (
          <p className="mt-3 text-xs text-amber-200/80">
            No GA4 events in facts yet — sync GA4 first, or enter an event name manually.
          </p>
        )}
      </form>

      <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="min-w-full text-left text-sm">
          <thead className="bg-white/5 text-[var(--muted)]">
            <tr>
              <th className="px-4 py-3 font-medium">Name</th>
              <th className="px-4 py-3 font-medium">Event</th>
              <th className="px-4 py-3 font-medium">Type</th>
              <th className="px-4 py-3 font-medium">Primary</th>
              <th className="px-4 py-3 font-medium">Active</th>
            </tr>
          </thead>
          <tbody>
            {conversions.map((conversion) => (
              <tr key={conversion.id} className="border-t border-[var(--border)]">
                <td className="px-4 py-3">{conversion.conversion_name}</td>
                <td className="px-4 py-3 text-[var(--muted)]">{conversion.event_name}</td>
                <td className="px-4 py-3">{conversion.conversion_type}</td>
                <td className="px-4 py-3">{conversion.is_primary ? "yes" : "no"}</td>
                <td className="px-4 py-3">{conversion.active ? "yes" : "no"}</td>
              </tr>
            ))}
            {conversions.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-[var(--muted)]">
                  No conversion definitions yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
