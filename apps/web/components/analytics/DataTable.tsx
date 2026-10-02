import Link from "next/link";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  align?: "left" | "right";
  className?: string;
  /**
   * Keep this cell clickable in a row that is itself a link.
   *
   * Row links are an overlay anchor and every other cell is
   * `pointer-events-none` so clicks fall through to it. A cell holding its own
   * control has to opt out, or the overlay swallows it.
   */
  interactive?: boolean;
  /**
   * Makes the header clickable, ordering by what this returns.
   *
   * Separate from `render` because what you read and what you sort by differ:
   * a chip reading "Near win" orders by how actionable it is, not by "N".
   */
  sortValue?: (row: T) => number | string | null;
  /**
   * Which way the first click should order this column.
   *
   * Biggest-first is right for a count and wrong for a ranking: opening
   * "Opportunity Type" on descending buries the quickest wins at the bottom.
   */
  sortInitial?: "asc" | "desc";
  render: (row: T) => ReactNode;
};

export type SortState = { key: string; dir: "asc" | "desc" };

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  title,
  className,
  emptyMessage = "No data for this period.",
  rowHref,
  rowLabel,
  sort,
  onSortChange,
}: {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  title?: string;
  className?: string;
  emptyMessage?: string;
  /**
   * Makes the whole row a link to this href. Rendered as an overlay anchor so
   * the row stays a real table row — wrapping <tr> in <a> is invalid HTML, and
   * a click handler would need a client component for what is just navigation.
   */
  rowHref?: (row: T) => string;
  rowLabel?: (row: T) => string;
  /** Current ordering. Columns with `sortValue` become clickable when set. */
  sort?: SortState | null;
  onSortChange?: (key: string) => void;
}) {
  const sortColumn = sort ? columns.find((column) => column.key === sort.key) : undefined;
  if (sortColumn?.sortValue) {
    const read = sortColumn.sortValue;
    const direction = sort?.dir === "asc" ? 1 : -1;
    rows = [...rows].sort((a, b) => {
      const left = read(a);
      const right = read(b);
      // Missing values sink, whichever way the column is pointing: they are
      // never the answer to "show me the biggest" or "the smallest".
      if (left === null && right === null) return 0;
      if (left === null) return 1;
      if (right === null) return -1;
      if (typeof left === "number" && typeof right === "number") {
        return (left - right) * direction;
      }
      return String(left).localeCompare(String(right)) * direction;
    });
  }

  if (rows.length === 0) {
    return (
      <div
        className={cn(
          "table-shell px-3 py-6 text-center text-xs text-[var(--text-secondary)]",
          className,
        )}
      >
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className={cn("table-shell overflow-x-auto", className)}>
      {title ? (
        <div className="border-b border-[var(--border)] px-3 py-2 text-xs font-semibold text-[var(--text-primary)]">
          {title}
        </div>
      ) : null}
      <table>
        <thead>
          <tr>
            {columns.map((column) => {
              const sortable = Boolean(column.sortValue && onSortChange);
              const active = sort?.key === column.key;
              return (
                <th
                  key={column.key}
                  className={cn(column.align === "right" && "text-right", column.className)}
                  aria-sort={
                    active ? (sort?.dir === "asc" ? "ascending" : "descending") : undefined
                  }
                >
                  {sortable ? (
                    <button
                      type="button"
                      onClick={() => onSortChange?.(column.key)}
                      className={cn(
                        "inline-flex items-center gap-1 hover:text-[var(--text-primary)]",
                        active && "text-[var(--text-primary)]",
                      )}
                    >
                      {column.header}
                      <span aria-hidden className="text-[9px] leading-none">
                        {active ? (sort?.dir === "asc" ? "▲" : "▼") : "⇅"}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const href = rowHref?.(row);
            return (
              <tr key={getRowKey(row)} className={href ? "row-linked" : undefined}>
                {columns.map((column, index) => (
                  <td
                    key={column.key}
                    className={cn(
                      column.align === "right" && "text-right tabular-nums",
                      href && "relative",
                      column.className,
                    )}
                  >
                    {href && index === 0 ? (
                      <Link
                        href={href}
                        aria-label={rowLabel?.(row) ?? "Open row"}
                        className="absolute inset-0 z-[1]"
                      />
                    ) : null}
                    <span
                      className={cn(
                        href && "relative z-[2]",
                        href && !column.interactive && "pointer-events-none",
                      )}
                    >
                      {column.render(row)}
                    </span>
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
