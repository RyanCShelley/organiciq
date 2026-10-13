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

// Searching keeps this table's own sort. It used to reset it.
{
  const query = { from: "2026-10-01", pages_sort: "ga4_sessions", pages_dir: "desc" };
  const t = tableControls(query, "/d", "pages", { keep: ["from"] });
  assert.equal(t.searchKeep.pages_sort, "ga4_sessions");
  assert.equal(t.searchKeep.pages_dir, "desc");
  assert.equal(t.searchKeep.from, "2026-10-01");
  // No sort chosen, so none is invented.
  assert.equal(tableControls({}, "/d", "pages").searchKeep.pages_sort, undefined);
}

// Sorting one table keeps the others' ordering and searches.
{
  const query = { channels_sort: "views", channels_dir: "asc", leads_q: "direct", pages_sort: "x" };
  const href = tableControls(query, "/d", "pages").sortHref("sessions", "desc");
  assert.ok(href.includes("channels_sort=views"));
  assert.ok(href.includes("channels_dir=asc"));
  assert.ok(href.includes("leads_q=direct"));
  // Its own old sort is replaced, not duplicated.
  assert.equal(href.split("pages_sort=").length, 2);
  assert.ok(href.includes("pages_sort=sessions"));
}

// Another table's search does not leak into this one's own box.
{
  const t = tableControls({ leads_q: "direct" }, "/d", "pages");
  assert.equal(t.searchValue, "");
  assert.equal(t.searchKeep.leads_q, "direct");
}

console.log("table-sort: all assertions passed");
