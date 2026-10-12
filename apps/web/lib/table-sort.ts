import type { SortState } from "@/components/analytics/DataTable";

export type Query = Record<string, string | string[] | undefined>;

/**
 * Sort and search for a server-rendered table, held in the URL.
 *
 * A header that needed React state could only work inside a client
 * component, which is why almost no table on the site could be sorted. A
 * link needs none, survives a refresh, and can be sent to somebody.
 *
 * Each table on a page gets its own `name`, so sorting Top pages does not
 * reorder Traffic by channel underneath it.
 */
export function tableControls(
  query: Query,
  base: string,
  name: string,
  options: { keep?: string[] } = {},
) {
  const sortParam = `${name}_sort`;
  const dirParam = `${name}_dir`;
  const searchParam = `${name}_q`;

  const key = typeof query[sortParam] === "string" ? (query[sortParam] as string) : null;
  const dir = query[dirParam] === "asc" ? "asc" : "desc";
  const search =
    typeof query[searchParam] === "string" ? (query[searchParam] as string).trim() : "";

  // Everything else on the URL stays: a filter, a date range and another
  // table's ordering are all somebody's current view.
  const carried = new URLSearchParams();
  for (const name of options.keep ?? []) {
    const value = query[name];
    if (typeof value === "string" && value) carried.set(name, value);
  }

  const sort: SortState | null = key ? { key, dir: dir as "asc" | "desc" } : null;

  return {
    sort,
    sortHref: (columnKey: string, nextDir: "asc" | "desc") => {
      const qs = new URLSearchParams(carried);
      if (search) qs.set(searchParam, search);
      qs.set(sortParam, columnKey);
      qs.set(dirParam, nextDir);
      return `${base}?${qs}`;
    },
    searchAction: base,
    searchParam,
    searchValue: search,
    searchKeep: Object.fromEntries(carried),
  };
}

/** Rows matching `search` across the fields a reader can actually see. */
export function filterRows<T>(
  rows: T[],
  search: string,
  read: (row: T) => (string | null | undefined)[],
): T[] {
  if (!search) return rows;
  const needle = search.toLowerCase();
  return rows.filter((row) =>
    read(row)
      .filter(Boolean)
      .some((field) => String(field).toLowerCase().includes(needle)),
  );
}
