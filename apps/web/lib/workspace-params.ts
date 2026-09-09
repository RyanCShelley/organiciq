"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useTransition } from "react";

export type RangeKey = "today" | "7d" | "14d" | "30d" | "90d" | "6m" | "12m" | "custom";

export const RANGE_OPTIONS: { key: RangeKey; label: string; days?: number }[] = [
  { key: "today", label: "Today", days: 1 },
  { key: "7d", label: "Last 7 days", days: 7 },
  { key: "14d", label: "Last 14 days", days: 14 },
  { key: "30d", label: "Last 30 days", days: 30 },
  { key: "90d", label: "Last 90 days", days: 90 },
  { key: "6m", label: "Last 6 months", days: 182 },
  { key: "12m", label: "Last 12 months", days: 365 },
  { key: "custom", label: "Custom" },
];

export function isoDaysAgo(days: number): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setUTCDate(to.getUTCDate() - (days - 1));
  return {
    from: from.toISOString().slice(0, 10),
    to: to.toISOString().slice(0, 10),
  };
}

export function detectRangeKey(from: string, to: string, explicit?: string | null): RangeKey {
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

export function formatDateLabel(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function useWorkspaceParams({
  clientId,
  from,
  to,
  persistDefault = false,
}: {
  clientId: string;
  from: string;
  to: string;
  persistDefault?: boolean;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [pending, startTransition] = useTransition();
  const didPersistDefault = useRef(false);

  const paramsFrom = searchParams.get("from");
  const paramsTo = searchParams.get("to");
  const activeFrom = paramsFrom || from;
  const activeTo = paramsTo || to;

  const rangeKey = useMemo(
    () => detectRangeKey(activeFrom, activeTo, searchParams.get("range")),
    [activeFrom, activeTo, searchParams],
  );

  useEffect(() => {
    if (!persistDefault) return;
    if (didPersistDefault.current || !clientId) return;
    didPersistDefault.current = true;
    document.cookie = `oiq_client_id=${clientId}; path=/; max-age=31536000`;
    const params = new URLSearchParams(searchParams.toString());
    // Keep date range in the URL; persist client via cookie (and path under /clients/).
    params.delete("clientId");
    if (activeFrom) params.set("from", activeFrom);
    if (activeTo) params.set("to", activeTo);
    params.set("range", rangeKey);
    const qs = params.toString();
    startTransition(() => {
      router.replace(qs ? `${pathname}?${qs}` : pathname);
      router.refresh();
    });
  }, [
    activeFrom,
    activeTo,
    clientId,
    pathname,
    persistDefault,
    rangeKey,
    router,
    searchParams,
    startTransition,
  ]);

  function apply(next: {
    clientId?: string;
    clientSlug?: string;
    from?: string;
    to?: string;
    range?: RangeKey;
  }) {
    const params = new URLSearchParams(searchParams.toString());
    const nextClientId = next.clientId ?? clientId;
    const nextFrom = next.from ?? activeFrom;
    const nextTo = next.to ?? activeTo;
    const nextRange = next.range ?? rangeKey;

    params.delete("clientId");
    if (nextClientId && !pathname.startsWith("/clients/")) {
      params.set("clientId", nextClientId);
    }
    params.set("from", nextFrom);
    params.set("to", nextTo);
    params.set("range", nextRange);

    document.cookie = `oiq_client_id=${nextClientId}; path=/; max-age=31536000`;
    document.cookie = `oiq_from=${nextFrom}; path=/; max-age=31536000`;
    document.cookie = `oiq_to=${nextTo}; path=/; max-age=31536000`;
    document.cookie = `oiq_range=${nextRange}; path=/; max-age=31536000`;

    const nextPath =
      next.clientSlug && pathname.startsWith("/clients/")
        ? pathname.replace(/^\/clients\/[^/]+/, `/clients/${next.clientSlug}`)
        : pathname;

    const qs = params.toString();
    startTransition(() => {
      router.push(qs ? `${nextPath}?${qs}` : nextPath);
      router.refresh();
    });
  }

  return {
    pending,
    activeFrom,
    activeTo,
    rangeKey,
    apply,
  };
}
