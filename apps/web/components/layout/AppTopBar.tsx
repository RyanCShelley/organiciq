"use client";

import { Download } from "lucide-react";
import { usePathname } from "next/navigation";

import {
  COMPARE_OPTIONS,
  TOPBAR_RANGE_OPTIONS,
  formatDateLabel,
  isoDaysAgo,
  useWorkspaceParams,
  type CompareMode,
  type RangeKey,
} from "@/lib/workspace-params";
import { resolvePageChrome } from "@/lib/page-chrome";
import { clientSlugFromPath } from "@/lib/navigation";
import type { Client } from "@/lib/api";

/**
 * Routes whose data actually varies with the selected period.
 *
 * Watch List, Annotations, All clients and the platform pages all read
 * current-state tables and never pass from/to to the API, so showing a date
 * picker there implies a filter that does not exist.
 */
const PERIOD_AWARE_TOOLS = ["dashboard", "content-opp", "decision-engine"];

function supportsPeriod(pathname: string): boolean {
  const parts = pathname.split("/").filter(Boolean);
  if (parts.length < 2) return false;
  return PERIOD_AWARE_TOOLS.includes(parts[1]);
}

/** Export ships the dashboard dataset, so it belongs on the dashboard. */
function supportsExport(pathname: string): boolean {
  const parts = pathname.split("/").filter(Boolean);
  return parts.length >= 2 && parts[1] === "dashboard";
}

export function AppTopBar({
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
  const pathname = usePathname();
  const { title, description } = resolvePageChrome(pathname);
  const { pending, activeFrom, activeTo, rangeKey, compareMode, apply } =
    useWorkspaceParams({
      clientId,
      from,
      to,
      persistDefault: true,
    });
  const isCustom = rangeKey === "custom";
  const showPeriod = supportsPeriod(pathname);

  // Export the client in the URL, not the cookie default the layout passes down.
  const pathSlug = clientSlugFromPath(pathname);
  const exportClientId =
    (pathSlug
      ? clients.find((client) => client.slug === pathSlug)?.id
      : null) ?? clientId;
  const canExport = supportsExport(pathname) && Boolean(exportClientId);

  const exportHref = `/api/export/dashboard?clientId=${encodeURIComponent(
    exportClientId,
  )}&from=${encodeURIComponent(activeFrom)}&to=${encodeURIComponent(activeTo)}`;

  function onRangeChange(key: RangeKey) {
    if (key === "custom") {
      apply({ range: "custom" });
      return;
    }
    const option = TOPBAR_RANGE_OPTIONS.find((row) => row.key === key);
    if (!option?.days) return;
    apply({ ...isoDaysAgo(option.days), range: key });
  }

  return (
    <div className="topbar-row">
      <div className="topbar-title min-w-0">
        <h1 className="page-title">{title}</h1>
        {description ? <p className="page-description">{description}</p> : null}
      </div>

      <div className="topbar-controls">
        {showPeriod ? (
          <>
            <span className="period-label">
              {formatDateLabel(activeFrom)} – {formatDateLabel(activeTo)}
            </span>

            <select
              aria-label="Timeframe"
              className="period-select"
              value={rangeKey}
              disabled={pending}
              onChange={(event) =>
                onRangeChange(event.target.value as RangeKey)
              }
            >
              {TOPBAR_RANGE_OPTIONS.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>

            {isCustom ? (
              <>
                <input
                  type="date"
                  aria-label="From date"
                  className="period-date"
                  value={activeFrom}
                  max={activeTo}
                  disabled={pending}
                  onChange={(event) =>
                    apply({ from: event.target.value, range: "custom" })
                  }
                />
                <span className="text-[var(--text-tertiary)]">–</span>
                <input
                  type="date"
                  aria-label="To date"
                  className="period-date"
                  value={activeTo}
                  min={activeFrom}
                  disabled={pending}
                  onChange={(event) =>
                    apply({ to: event.target.value, range: "custom" })
                  }
                />
              </>
            ) : null}

            <select
              aria-label="Compare mode"
              className="period-select"
              value={compareMode}
              disabled={pending}
              onChange={(event) =>
                apply({ compare: event.target.value as CompareMode })
              }
            >
              {COMPARE_OPTIONS.map((option) => (
                <option key={option.key} value={option.key}>
                  {option.label}
                </option>
              ))}
            </select>
          </>
        ) : null}

        {canExport ? (
          <a className="btn-export" href={exportHref} download>
            <Download className="h-3.5 w-3.5" aria-hidden />
            Export data
          </a>
        ) : null}
      </div>
    </div>
  );
}
