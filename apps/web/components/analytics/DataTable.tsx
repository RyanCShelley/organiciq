import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type DataTableColumn<T> = {
  key: string;
  header: string;
  align?: "left" | "right";
  className?: string;
  render: (row: T) => ReactNode;
};

export function DataTable<T>({
  columns,
  rows,
  getRowKey,
  title,
  className,
  emptyMessage = "No data for this period.",
}: {
  columns: DataTableColumn<T>[];
  rows: T[];
  getRowKey: (row: T) => string;
  title?: string;
  className?: string;
  emptyMessage?: string;
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
          {rows.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn(
                    column.align === "right" && "text-right tabular-nums",
                    column.className,
                  )}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
