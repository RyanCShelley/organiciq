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
  render: (row: T) => ReactNode;
};

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  title,
  className,
  emptyMessage = "No data for this period.",
  rowHref,
  rowLabel,
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
}) {
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
            {columns.map((column) => (
              <th
                key={column.key}
                className={cn(column.align === "right" && "text-right", column.className)}
              >
                {column.header}
              </th>
            ))}
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
