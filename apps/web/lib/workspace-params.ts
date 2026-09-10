"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useTransition } from "react";

import {
  COMPARE_OPTIONS,
  RANGE_OPTIONS,
  TOPBAR_RANGE_OPTIONS,
  comparisonLabelFor,
  detectRangeKey,
  formatDateLabel,
  isoDaysAgo,
  parseCompareMode,
  type CompareMode,
  type RangeKey,
} from "@/lib/date-range";

// Re-exported so client components keep a single import site.
export {
  COMPARE_OPTIONS,
  RANGE_OPTIONS,
  TOPBAR_RANGE_OPTIONS,
  comparisonLabelFor,
  detectRangeKey,
  formatDateLabel,
  isoDaysAgo,
  parseCompareMode,
};
export type { CompareMode, RangeKey };

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

  const compareMode = parseCompareMode(searchParams.get("compare") ?? undefined);

  useEffect(() => {
    if (!persistDefault) return;
    if (didPersistDefault.current || !clientId) return;
    didPersistDefault.current = true;
    document.cookie = `oiq_client_id=${clientId}; path=/; max-age=31536000`;
    const params = new URLSearchParams(searchParams.toString());
    // Keep date range in the URL; client lives in the path (or cookie).
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
    compare?: CompareMode;
  }) {
    const params = new URLSearchParams(searchParams.toString());
    const nextClientId = next.clientId ?? clientId;
    const nextFrom = next.from ?? activeFrom;
    const nextTo = next.to ?? activeTo;
    const nextRange = next.range ?? rangeKey;
    const nextCompare = next.compare ?? compareMode;

    params.delete("clientId");
    // Prefer slug in the path for account tools and /clients/* — do not put clientId in the query.
    const onClientsPath = pathname.startsWith("/clients/");
    const accountMatch = pathname.match(
      /^\/([^/]+)\/(dashboard|watch-list|content-opp|decision-engine|annotations)(\/|$)/,
    );
    if (nextClientId && !onClientsPath && !accountMatch) {
      params.set("clientId", nextClientId);
    }
    params.set("from", nextFrom);
    params.set("to", nextTo);
    params.set("range", nextRange);
    params.set("compare", nextCompare);

    document.cookie = `oiq_client_id=${nextClientId}; path=/; max-age=31536000`;
    document.cookie = `oiq_from=${nextFrom}; path=/; max-age=31536000`;
    document.cookie = `oiq_to=${nextTo}; path=/; max-age=31536000`;
    document.cookie = `oiq_range=${nextRange}; path=/; max-age=31536000`;
    document.cookie = `oiq_compare=${nextCompare}; path=/; max-age=31536000`;

    let nextPath = pathname;
    if (next.clientSlug) {
      if (onClientsPath) {
        nextPath = pathname.replace(/^\/clients\/[^/]+/, `/clients/${next.clientSlug}`);
      } else if (accountMatch) {
        nextPath = pathname.replace(/^\/[^/]+/, `/${next.clientSlug}`);
      }
    }

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
    compareMode,
    apply,
  };
}
