"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useTransition } from "react";

import type { Client } from "@/lib/api";

type RangeKey = "today" | "7d" | "14d" | "30d" | "90d" | "6m" | "12m" | "custom";

const RANGE_OPTIONS: { key: RangeKey; label: string; days?: number }[] = [
  { key: "today", label: "Today", days: 1 },
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "14d", label: "Last 14 days", days: 14 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "90d", label: "Last 90 days", days: 90 },
  { key: "6m", label: "Last 6 months", days: 182 },
  { key: "12m", label: "Last 12 months", days: 365 },
  { key: "custom", label: "Custom" },
];

function isoDaysAgo(days: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setUTCDate(to.getUTCDate() - (days - 1));
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

function detectRangeKey(from: string, to: string, explicit?: string | null): RangeKey {
  if (explicit === "custom") return "custom";
  if (explicit && RANGE_OPTIONS.some((o) => o.key === explicit)) {
    return explicit as RangeKey;
  }

  for (const option of RANGE_OPTIONS) {
    if (!option.days) continue;
    const expected = isoDaysAgo(option.days);
    if (expected.from === from && expected.to === to) return option.key;
  }
  return "custom";
}

export function ClientDateControls({
  clients,
  clientId,
  from,
  to,
}: {
  clients: Client[];
  clientId: string;
  from: string;
  to: string;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();
  const didPersistDefault = useRef(false);

  const rangeKey = useMemo(
    () => detectRangeKey(from, to, searchParams.get("range")),
    [from, to, searchParams],
  );
  const isCustom = rangeKey === "custom";

  useEffect(() => {
    if (didPersistDefault.current || !clientId) return;
    if (searchParams.get("clientId")) return;
    didPersistDefault.current = true;
    document.cookie = `oiq_client_id=${clientId}; path=/; max-age=31536000`;
    const params = new URLSearchParams(searchParams.toString());
    params.set("clientId", clientId);
    if (from) params.set("from", from);
    if (to) params.set("to", to);
    params.set("range", rangeKey);
    startTransition(() => {
      router.replace(`${pathname}?${params.toString()}`);
      router.refresh();
    });
  }, [clientId, from, to, pathname, rangeKey, router, searchParams, startTransition]);

  function apply(next: {
    clientId?: string;
    from?: string;
    to?: string;
    range?: RangeKey;
  }) {
    const params = new URLSearchParams(searchParams.toString());
    const nextClientId = next.clientId ?? clientId;
    const nextFrom = next.from ?? from;
    const nextTo = next.to ?? to;
    const nextRange = next.range ?? rangeKey;

    if (nextClientId) params.set("clientId", nextClientId);
    params.set("from", nextFrom);
    params.set("to", nextTo);
    params.set("range", nextRange);

    document.cookie = `oiq_client_id=${nextClientId}; path=/; max-age=31536000`;
    document.cookie = `oiq_from=${nextFrom}; path=/; max-age=31536000`;
    document.cookie = `oiq_to=${nextTo}; path=/; max-age=31536000`;
    document.cookie = `oiq_range=${nextRange}; path=/; max-age=31536000`;

    startTransition(() => {
      router.push(`${pathname}?${params.toString()}`);
      router.refresh();
    });
  }

  function onRangeChange(key: RangeKey) {
    if (key === "custom") {
      apply({ range: "custom" });
      return;
    }
    const option = RANGE_OPTIONS.find((o) => o.key === key);
    if (!option?.days) return;
    const window = isoDaysAgo(option.days);
    apply({ ...window, range: key });
  }

  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
        Client
        <select
          className="min-w-[220px] rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
          value={clientId}
          disabled={pending || clients.length === 0}
          onChange={(e) => apply({ clientId: e.target.value })}
        >
          {clients.length === 0 ? <option value="">No clients</option> : null}
          {clients.map((c) => (
            <option key={c.id} value={c.id}>
              {c.client_name}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
        Date range
        <select
          className="min-w-[180px] rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
          value={rangeKey}
          disabled={pending}
          onChange={(e) => onRangeChange(e.target.value as RangeKey)}
        >
          {RANGE_OPTIONS.map((option) => (
            <option key={option.key} value={option.key}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      {isCustom ? (
        <>
          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            From
            <input
              type="date"
              className="rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
              value={from}
              onChange={(e) => apply({ from: e.target.value, range: "custom" })}
            />
          </label>

          <label className="flex flex-col gap-1 text-xs text-[var(--muted)]">
            To
            <input
              type="date"
              className="rounded-lg border border-[var(--border)] bg-[#0b1220] px-3 py-2 text-sm text-white"
              value={to}
              onChange={(e) => apply({ to: e.target.value, range: "custom" })}
            />
          </label>
        </>
      ) : null}
    </div>
  );
}
