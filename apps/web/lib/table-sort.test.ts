// Run with: npx tsx apps/web/lib/table-sort.test.ts
import assert from "node:assert/strict";

import { filterRows, tableControls } from "./table-sort";

// Each table on a page keeps its own ordering: sorting Top pages must not
// reorder Traffic by channel underneath it.
{
  const query = { pages_sort: "ga4_sessions", pages_dir: "asc", channels_sort: "views" };
  const pages = tableControls(query, "/d", "pages");
  const channels = tableControls(query, "/d", "channels");
  assert.deepEqual(pages.sort, { key: "ga4_sessions", dir: "asc" });
  assert.deepEqual(channels.sort, { key: "views", dir: "desc" });
}

// A sort click carries the date range, or it silently resets the window.
{
  const query = { from: "2026-10-01", to: "2026-10-12", compare: "prev" };
  const t = tableControls(query, "/d", "pages", { keep: ["from", "to", "compare"] });
  const href = t.sortHref("sessions", "desc");
  assert.ok(href.includes("from=2026-10-01"));
  assert.ok(href.includes("to=2026-10-12"));
  assert.ok(href.includes("compare=prev"));
  assert.ok(href.includes("pages_sort=sessions"));
}

// And carries the search, so ordering results does not throw them away.
{
  const t = tableControls({ pages_q: "blog" }, "/d", "pages");
  assert.ok(t.sortHref("sessions", "desc").includes("pages_q=blog"));
  assert.equal(t.searchValue, "blog");
}

// Matched on what a reader can see, and case-insensitively.
{
  const rows = [{ a: "Blog post", b: 1300 }, { a: "Contact", b: 42 }];
  assert.equal(filterRows(rows, "blog", (r) => [r.a]).length, 1);
  assert.equal(filterRows(rows, "BLOG", (r) => [r.a]).length, 1);
  // Not every column: searching "1300" should not match a word count.
  assert.equal(filterRows(rows, "1300", (r) => [r.a]).length, 0);
  assert.equal(filterRows(rows, "", (r) => [r.a]).length, 2);
}

console.log("table-sort: all assertions passed");
