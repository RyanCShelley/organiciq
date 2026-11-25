"use client";

import Link from "next/link";
import { ArrowDown, ArrowUp, ArrowUpDown, Plus, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { ClientFavicon } from "@/components/layout/ClientFavicon";
import { inputClass } from "@/components/ui/form";
import type { ClientOverviewItem, ClientsOverviewResponse } from "@/lib/overview";

type SortKey =
  | "client_name"
  | "status"
  | "impressions"
  | "avg_position"
  | "organic_sessions"
  | "clicks"
  | "leads"
  | "updated";

type SortDir = "asc" | "desc";

type StatusFilter = "all" | "active" | "onboarding" | "missing" | "paused" | "archived";

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "onboarding", label: "Onboarding" },
  { value: "missing", label: "Missing setup" },
  { value: "paused", label: "Paused" },
  { value: "archived", label: "Archived" },
];

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  active: { label: "Active", className: "bg-green-100 text-green-800" },
  onboarding: { label: "Onboarding", className: "bg-amber-50 text-amber-800" },
  paused: { label: "Paused", className: "bg-[#eceef2] text-[#4a5468]" },
  archived: { label: "Archived", className: "bg-slate-100 text-[var(--text-secondary)]" },
};

const DEFAULT_DIR: Record<SortKey, SortDir> = {
  client_name: "asc",
  status: "asc",
  impressions: "desc",
  avg_position: "asc",
  organic_sessions: "desc",
  clicks: "desc",
  leads: "desc",
  updated: "desc",
};

function formatNumber(n: number | null | undefined, digits = 0): string {
  if (n == null) return "–";
  return n.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function formatShortDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function latestUpdatedIso(row: ClientOverviewItem): string | null {
  if (row.gsc_through && row.ga4_through) {
    return row.gsc_through >= row.ga4_through ? row.gsc_through : row.ga4_through;
  }
  return row.gsc_through ?? row.ga4_through ?? null;
}

function sortValue(row: ClientOverviewItem, key: SortKey): string | number | null {
  switch (key) {
    case "client_name":
      return row.client_name;
    case "status":
      return row.status;
    case "impressions":
      return row.impressions;
    case "avg_position":
      return row.avg_position;
    case "organic_sessions":
      return row.organic_sessions;
    case "clicks":
      return row.clicks;
    case "leads":
      return row.leads;
    case "updated":
      return latestUpdatedIso(row);
  }
}

function TrendDelta({ pct }: { pct: number | null }) {
  if (pct == null) return null;
  if (Math.abs(pct) < 1) {
    return <span className="ml-1.5 text-xs text-[var(--text-secondary)]">flat</span>;
  }
  if (pct > 0) {
    return (
      <span className="ml-1.5 text-xs font-semibold text-green-700">
        ▲ {Math.abs(pct).toFixed(0)}%
      </span>
    );
  }
  return (
    <span className="ml-1.5 text-xs font-semibold text-red-700">
      ▼ {Math.abs(pct).toFixed(0)}%
    </span>
  );
}

function PositionDelta({ change }: { change: number | null | undefined }) {
  if (change == null) return null;
  if (Math.abs(change) < 0.1) {
    return <span className="ml-1.5 text-xs text-[var(--text-secondary)]">flat</span>;
  }
  if (change > 0) {
    return (
      <span className="ml-1.5 text-xs font-semibold text-green-700">
        ▲ {change.toFixed(1)}
      </span>
    );
  }
  return (
    <span className="ml-1.5 text-xs font-semibold text-red-700">
      ▼ {Math.abs(change).toFixed(1)}
    </span>
  );
}

function PacingBar({ pct }: { pct: number | null | undefined }) {
  if (pct == null) return null;
  const clamped = Math.min(Math.max(pct, 0), 100);
  const color =
    pct >= 95 ? "bg-[var(--brand-teal)]" : pct >= 75 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="ml-auto mt-1 h-1.5 w-24 overflow-hidden rounded-full bg-[#eceef2]">
      <div className={`h-full rounded-full ${color}`} style={{ width: `${clamped}%` }} />
    </div>
  );
}

function SortHeader({
  label,
  column,
  activeKey,
  dir,
  align = "left",
  onSort,
}: {
  label: string;
  column: SortKey;
  activeKey: SortKey;
  dir: SortDir;
  align?: "left" | "right";
  onSort: (column: SortKey) => void;
}) {
  const isActive = activeKey === column;
  const ariaSort = isActive ? (dir === "asc" ? "ascending" : "descending") : "none";
  const Icon = !isActive ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;

  return (
    <th
      scope="col"
      aria-sort={ariaSort}
      className={`px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)] ${
        align === "right" ? "text-right" : "text-left"
      }`}
    >
      <button
        type="button"
        onClick={() => onSort(column)}
        className={`inline-flex items-center gap-1 rounded px-1 py-0.5 transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-teal)] ${
          isActive ? "text-[var(--text-primary)]" : ""
        }`}
      >
        <span>{label}</span>
        <Icon size={13} aria-hidden className={isActive ? "opacity-90" : "opacity-45"} />
      </button>
    </th>
  );
}

export function AllClientsOverview({ data }: { data: ClientsOverviewResponse }) {
  const { window, clients } = data;
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("client_name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  function handleSort(column: SortKey) {
    if (sortKey === column) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(column);
      setSortDir(DEFAULT_DIR[column]);
    }
  }

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = clients.filter((row) => {
      if (statusFilter === "missing") {
        if ((row.missing_setup ?? []).length === 0) return false;
      } else if (statusFilter !== "all" && row.status !== statusFilter) {
        return false;
      }
      if (!q) return true;
      return (
        row.client_name.toLowerCase().includes(q) ||
        row.domain.toLowerCase().includes(q) ||
        (row.group_name ?? "").toLowerCase().includes(q)
      );
    });

    return [...filtered].sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);

      // Nulls-last regardless of sort direction
      if (av == null && bv == null) return a.client_name.localeCompare(b.client_name);
      if (av == null) return 1;
      if (bv == null) return -1;

      let cmp = 0;
      if (typeof av === "string" && typeof bv === "string") {
        cmp = av.localeCompare(bv);
      } else {
        cmp = Number(av) - Number(bv);
      }
      if (cmp === 0) return a.client_name.localeCompare(b.client_name);
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [clients, query, statusFilter, sortKey, sortDir]);

  const isFiltered = query.trim().length > 0 || statusFilter !== "all";
  const missingClientsCount = clients.filter((c) => (c.missing_setup ?? []).length > 0).length;
  const onboardingCount = clients.filter((c) => c.status === "onboarding").length;
  const behindLeadsCount = clients.filter(
    (c) => c.lead_goal_progress_pct != null && c.lead_goal_progress_pct < 85,
  ).length;
  const readyCount = clients.length - missingClientsCount;

  return (
    <section className="w-full space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold text-[var(--text-primary)]">
            All clients
          </h1>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {clients.length} {clients.length === 1 ? "client" : "clients"} · Last {window.days} days (
            {formatShortDate(window.from_date)} – {formatShortDate(window.to_date)}) vs prior{" "}
            {window.days} days
          </p>
        </div>
        <Link
          href="/new-client"
          className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white hover:bg-[var(--brand-dark-2)]"
        >
          <Plus size={16} aria-hidden />
          Add client
        </Link>
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
            Total clients
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-[var(--text-primary)]">
            {clients.length}
          </div>
          <div className="text-xs text-[var(--text-secondary)]">{onboardingCount} onboarding</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
            Setup / data gaps
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-rose-700">
            {missingClientsCount}
          </div>
          <div className="text-xs text-[var(--text-secondary)]">
            Missing baseline, watchlist, or tracking
          </div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
            Behind lead goal (&lt;85%)
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-amber-700">
            {behindLeadsCount}
          </div>
          <div className="text-xs text-[var(--text-secondary)]">30-day checkpoint pacing</div>
        </div>
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
            Ready &amp; tracking
          </div>
          <div className="mt-1 text-2xl font-bold tabular-nums text-green-700">
            {readyCount}
          </div>
          <div className="text-xs text-[var(--text-secondary)]">All 3 pillars configured</div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative w-64 max-w-full">
            <Search
              size={15}
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)]"
            />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter by client or domain…"
              aria-label="Filter clients"
              className={`${inputClass} pl-9`}
            />
          </div>

          <div
            role="group"
            aria-label="Filter by status"
            className="inline-flex rounded-lg border border-[var(--border)] bg-[var(--surface)] p-0.5 text-xs font-medium"
          >
            {STATUS_OPTIONS.map((opt) => {
              const active = statusFilter === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setStatusFilter(opt.value)}
                  aria-pressed={active}
                  className={`rounded-md px-2.5 py-1.5 transition-colors ${
                    active
                      ? "bg-[var(--brand-dark)] text-white"
                      : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
        </div>

        {isFiltered ? (
          <p className="text-xs font-medium text-[var(--text-secondary)]">
            Showing {rows.length} of {clients.length}
          </p>
        ) : null}
      </div>

      <div className="overflow-x-auto rounded-xl border border-[var(--border)] bg-[var(--surface)]">
        <table className="w-full border-collapse text-sm">
          <thead className="border-b border-[var(--border)] bg-[var(--background)]">
            <tr className="border-b border-[var(--border)] bg-slate-100/70 text-[10.5px] font-semibold uppercase tracking-wider text-[var(--text-secondary)]">
              <th colSpan={2} className="px-4 py-1.5 text-left">
                Client &amp; Readiness
              </th>
              <th colSpan={2} className="border-l border-[var(--border)] px-4 py-1.5 text-right">
                Visibility (Search Presence)
              </th>
              <th colSpan={2} className="border-l border-[var(--border)] px-4 py-1.5 text-right">
                Traffic (Visits &amp; Clicks)
              </th>
              <th className="border-l border-[var(--border)] px-4 py-1.5 text-right">
                Leads
              </th>
              <th className="border-l border-[var(--border)] px-4 py-1.5 text-right">
                Data Freshness
              </th>
            </tr>
            <tr>
              <SortHeader
                label="Client"
                column="client_name"
                activeKey={sortKey}
                dir={sortDir}
                onSort={handleSort}
              />
              <SortHeader
                label="Status & Missing Setup"
                column="status"
                activeKey={sortKey}
                dir={sortDir}
                onSort={handleSort}
              />
              <SortHeader
                label="Impressions (GSC+Bing)"
                column="impressions"
                activeKey={sortKey}
                dir={sortDir}
                align="right"
                onSort={handleSort}
              />
              <SortHeader
                label="Avg Position (Δ)"
                column="avg_position"
                activeKey={sortKey}
                dir={sortDir}
                align="right"
                onSort={handleSort}
              />
              <SortHeader
                label="Sessions (Org / Total)"
                column="organic_sessions"
                activeKey={sortKey}
                dir={sortDir}
                align="right"
                onSort={handleSort}
              />
              <SortHeader
                label="Search Clicks"
                column="clicks"
                activeKey={sortKey}
                dir={sortDir}
                align="right"
                onSort={handleSort}
              />
              <SortHeader
                label="Leads & Goal"
                column="leads"
                activeKey={sortKey}
                dir={sortDir}
                align="right"
                onSort={handleSort}
              />
              <SortHeader
                label="Updated"
                column="updated"
                activeKey={sortKey}
                dir={sortDir}
                align="right"
                onSort={handleSort}
              />
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            {rows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-10 text-center text-sm text-[var(--text-secondary)]">
                  No clients match the current filter.
                </td>
              </tr>
            ) : (
              rows.map((row) => {
                const badge = STATUS_BADGE[row.status] ?? {
                  label: row.status,
                  className: "bg-slate-100 text-[var(--text-secondary)]",
                };
                const goal = row.current_lead_goal ?? row.monthly_lead_goal;
                const missing = row.missing_setup ?? [];

                return (
                  <tr
                    key={row.id}
                    className="transition-colors hover:bg-[var(--background)]"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/${row.slug}/review`}
                        className="group flex items-center gap-3"
                      >
                        <ClientFavicon client={row} size={28} />
                        <div className="min-w-0">
                          <div className="truncate font-semibold text-[var(--text-primary)] group-hover:text-[var(--brand-teal-hover)]">
                            {row.client_name}
                          </div>
                          <div className="truncate text-xs text-[var(--text-secondary)]">
                            {row.domain}
                            {row.group_name ? ` · ${row.group_name}` : ""}
                          </div>
                        </div>
                      </Link>
                    </td>

                    <td className="px-4 py-3 align-middle">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span
                          className={`inline-flex whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-semibold ${badge.className}`}
                        >
                          {badge.label}
                        </span>
                        {row.service_mode === "consulting" ? (
                          <span className="inline-flex whitespace-nowrap rounded-full bg-[#e6f7f5] px-2 py-0.5 text-xs font-semibold text-[#00665f]">
                            Consulting
                          </span>
                        ) : null}
                      </div>
                      <div className="mt-1.5 flex flex-wrap gap-1">
                        {missing.length > 0 ? (
                          missing.map((item) => (
                            <span
                              key={item}
                              className="inline-flex whitespace-nowrap rounded border border-rose-200 bg-rose-50 px-1.5 py-0.5 text-[10.5px] font-semibold text-rose-700"
                            >
                              {item}
                            </span>
                          ))
                        ) : (
                          <span className="inline-flex whitespace-nowrap rounded border border-green-200 bg-green-50 px-1.5 py-0.5 text-[10.5px] font-semibold text-green-700">
                            All set
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="border-l border-slate-100 px-4 py-3 text-right align-middle tabular-nums">
                      <div className="font-medium text-[var(--text-primary)]">
                        {formatNumber(row.impressions)}
                        <TrendDelta pct={row.impressions_change_pct} />
                      </div>
                      {row.current_impressions_goal != null ? (
                        <div className="text-xs text-[var(--text-secondary)]">
                          goal {formatNumber(row.current_impressions_goal)}
                          {row.impressions_goal_progress_pct != null
                            ? ` (${Math.round(row.impressions_goal_progress_pct)}%)`
                            : ""}
                          <PacingBar pct={row.impressions_goal_progress_pct} />
                        </div>
                      ) : null}
                    </td>

                    <td className="px-4 py-3 text-right align-middle tabular-nums">
                      <div className="font-medium text-[var(--text-primary)]">
                        {row.avg_position != null ? row.avg_position.toFixed(1) : "–"}
                        <PositionDelta change={row.avg_position_change} />
                      </div>
                      <div className="text-xs text-[var(--text-secondary)]">vs prior 30d</div>
                    </td>

                    <td className="border-l border-slate-100 px-4 py-3 text-right align-middle tabular-nums">
                      <div className="font-medium text-[var(--text-primary)]">
                        {formatNumber(row.organic_sessions)}
                        <TrendDelta pct={row.organic_change_pct} />
                      </div>
                      {row.total_sessions != null || row.current_sessions_goal != null ? (
                        <div className="text-xs text-[var(--text-secondary)]">
                          {row.total_sessions != null ? `${formatNumber(row.total_sessions)} total` : ""}
                          {row.current_sessions_goal != null
                            ? `${row.total_sessions != null ? " · " : ""}goal ${formatNumber(row.current_sessions_goal)}${row.sessions_goal_progress_pct != null ? ` (${Math.round(row.sessions_goal_progress_pct)}%)` : ""}`
                            : ""}
                          <PacingBar pct={row.sessions_goal_progress_pct} />
                        </div>
                      ) : null}
                    </td>

                    <td className="px-4 py-3 text-right align-middle tabular-nums">
                      <div className="font-medium text-[var(--text-primary)]">
                        {formatNumber(row.clicks)}
                        <TrendDelta pct={row.clicks_change_pct ?? null} />
                      </div>
                      {row.current_clicks_goal != null ? (
                        <div className="text-xs text-[var(--text-secondary)]">
                          goal {formatNumber(row.current_clicks_goal)}
                          {row.clicks_goal_progress_pct != null
                            ? ` (${Math.round(row.clicks_goal_progress_pct)}%)`
                            : ""}
                          <PacingBar pct={row.clicks_goal_progress_pct} />
                        </div>
                      ) : (
                        <div className="text-xs text-[var(--text-secondary)]">search clicks</div>
                      )}
                    </td>

                    <td className="border-l border-slate-100 px-4 py-3 text-right align-middle tabular-nums">
                      <div className="font-medium text-[var(--text-primary)]">
                        {formatNumber(row.leads)}
                        <TrendDelta pct={row.leads_change_pct} />
                      </div>
                      {row.leads != null || goal != null ? (
                        <div className="text-xs text-[var(--text-secondary)]">
                          {row.lead_label}
                          {goal != null
                            ? ` · goal ${formatNumber(goal)}${row.lead_goal_progress_pct != null ? ` (${Math.round(row.lead_goal_progress_pct)}%)` : ""}`
                            : ""}
                          <PacingBar pct={row.lead_goal_progress_pct} />
                        </div>
                      ) : null}
                    </td>

                    <td className="border-l border-slate-100 px-4 py-3 text-right align-middle text-xs tabular-nums text-[var(--text-secondary)]">
                      <div className="space-y-0.5">
                        <div>
                          GSC{" "}
                          {row.gsc_through ? (
                            formatShortDate(row.gsc_through)
                          ) : (
                            <span className="font-semibold text-rose-700">Missing</span>
                          )}
                        </div>
                        <div>
                          GA4{" "}
                          {row.ga4_through ? (
                            formatShortDate(row.ga4_through)
                          ) : (
                            <span className="font-semibold text-rose-700">Missing</span>
                          )}
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
