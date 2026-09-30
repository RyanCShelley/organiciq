import Link from "next/link";

import { DataTable } from "@/components/analytics/DataTable";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { CrawlFilters, CRAWL_FILTERS, CELL_FILTER_PARAMS, hrefWith } from "@/components/analytics/CrawlFilters";
import { CrawlPageDetail } from "@/components/analytics/CrawlPageDetail";
import { RunCrawlButton } from "@/components/analytics/RunCrawlButton";
import {
  apiFetch,
  type CrawlPageDetail as PageDetail,
  type CrawledPagesPayload,
  type StructuredDataPayload,
} from "@/lib/api";
import { requireAccountClient } from "@/lib/account-routes.server";
import { accountToolHref } from "@/lib/account-routes";
import { clientHref } from "@/lib/client-path";

type CrawlTab = "pages" | "schema";

const EMPTY_PAGES: CrawledPagesPayload = {
  crawled_at: null,
  total_pages: 0,
  indexable_pages: 0,
  orphaned_pages: 0,
  sitemap_found: false,
  pages_in_sitemap: 0,
  matched_pages: 0,
  pagination_pages: 0,
  last_crawl_note: null,
  items: [],
  truncated: false,
};

const EMPTY_SCHEMA: StructuredDataPayload = {
  crawled_at: null,
  indexable_pages: 0,
  pages_with_descriptive_schema: 0,
  total_blocks: 0,
  invalid_blocks: 0,
  types: [],
  gaps: [],
  truncated: false,
};

const ISSUE_LABEL: Record<string, string> = {
  invalid: "Unparseable",
  missing: "None at all",
  boilerplate_only: "Boilerplate only",
};

function resolveTab(raw: string | string[] | undefined): CrawlTab {
  return raw === "schema" ? "schema" : "pages";
}

function formatDate(iso: string | null): string | null {
  if (!iso) return null;
  const parsed = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Path only — the domain is the same on every row and just costs width. */
function pathOf(url: string): string {
  try {
    const { pathname, search } = new URL(url);
    return `${pathname}${search}` || "/";
  } catch {
    return url;
  }
}

function Stat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "warning";
}) {
  return (
    <div className="rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface)] px-4 py-3">
      <div className="text-[11.5px] font-semibold text-[var(--text-tertiary)]">{label}</div>
      <div
        className={`mt-1 font-[family-name:var(--font-display)] text-[24px] font-black leading-none tracking-[-0.02em] ${
          tone === "warning" ? "text-[var(--warning)]" : "text-[var(--text-primary)]"
        }`}
      >
        {value}
      </div>
    </div>
  );
}

/**
 * A table cell that filters the list by its own value.
 *
 * Clicking the value that is already filtered clears it, so the same cell is
 * both the way in and the way out and there is no hunting for a reset.
 */
function FilterCell({
  base,
  active,
  param,
  value,
  children,
}: {
  base: string;
  active: Record<string, string>;
  param: string;
  value: string;
  children: React.ReactNode;
}) {
  const on = active[param] === value;
  return (
    <Link
      href={hrefWith(base, active, param, on ? "" : value)}
      className={
        on
          ? "-mx-1 rounded px-1 ring-1 ring-[var(--brand-teal-hover)]"
          : "-mx-1 rounded px-1 hover:bg-[var(--surface-muted)]"
      }
      title={on ? `Stop filtering by ${param}` : `Show only these`}
      scroll={false}
    >
      {children}
    </Link>
  );
}

export default async function SiteCrawlPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clientSlug } = await params;
  const query = await searchParams;
  const client = await requireAccountClient(clientSlug, "site-crawl");
  const clientId = client.id;
  const tab = resolveTab(query.tab);
  const selectedUrl = typeof query.url === "string" ? query.url : null;
  // Both the chip row and the table's own cells write to the query string, so
  // every filter has to be read here — not just the ones with a chip.
  const filters: Record<string, string> = {};
  for (const group of CRAWL_FILTERS) {
    const value = query[group.param];
    filters[group.param] = typeof value === "string" ? value : group.defaultValue ?? "";
  }
  for (const param of CELL_FILTER_PARAMS) {
    const value = query[param];
    filters[param] = typeof value === "string" ? value : "";
  }

  let pages: CrawledPagesPayload = EMPTY_PAGES;
  let schema: StructuredDataPayload = EMPTY_SCHEMA;
  let detail: PageDetail | null = null;
  let error: string | null = null;

  try {
    if (tab === "pages") {
      const qs = new URLSearchParams();
      for (const [param, value] of Object.entries(filters)) {
        if (value) qs.set(param, value);
      }
      const suffix = qs.toString();
      pages = await apiFetch<CrawledPagesPayload>(
        suffix ? `/site-crawl/pages?${suffix}` : "/site-crawl/pages",
        { clientId },
      );
      if (selectedUrl) {
        detail = await apiFetch<PageDetail>(
          `/site-crawl/page?url=${encodeURIComponent(selectedUrl)}`,
          { clientId },
        );
      }
    } else {
      schema = await apiFetch<StructuredDataPayload>("/site-crawl/schema", { clientId });
    }
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load the site crawl";
  }

  const crawledAt = formatDate(tab === "pages" ? pages.crawled_at : schema.crawled_at);
  const neverCrawled =
    !error && (tab === "pages" ? pages.total_pages === 0 : schema.indexable_pages === 0);

  const tabs: { id: CrawlTab; label: string }[] = [
    { id: "pages", label: "Pages" },
    { id: "schema", label: "Structured data" },
  ];
  const base = accountToolHref(client.slug, "site-crawl");
  // Keeps the active filters when opening or closing a page's detail.
  const filterQs = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value) filterQs.set(key, value);
  }
  const listHref = filterQs.toString() ? `${base}?${filterQs}` : base;
  const detailHref = (url: string) => {
    const qs = new URLSearchParams(filterQs);
    qs.set("url", url);
    return `${base}?${qs}`;
  };

  return (
    <section>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="segmented" role="tablist" aria-label="Site crawl tabs">
          {tabs.map((item) => (
            <Link
              key={item.id}
              href={item.id === "pages" ? base : `${base}?tab=${item.id}`}
              className={
                tab === item.id ? "segmented-item segmented-item-active" : "segmented-item"
              }
            >
              {item.label}
            </Link>
          ))}
        </div>
        <div className="flex items-start gap-3">
          {crawledAt ? (
            <span className="self-center font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
              Crawled {crawledAt}
            </span>
          ) : null}
          <RunCrawlButton clientId={clientId} />
        </div>
      </div>

      {error ? (
        <Alert variant="danger" className="mt-4">
          {error}
        </Alert>
      ) : null}

      {neverCrawled ? (
        <Alert variant="info" className="mt-4">
          This site hasn&rsquo;t been crawled yet. Crawls run weekly and each client has
          its own day in the cycle, so a newly added client waits for its slot &mdash; or
          press <strong>Run crawl</strong> above. The page limit and an optional sitemap
          URL are in{" "}
          <Link href={clientHref(client.slug, "")} className="font-medium underline">
            Client settings
          </Link>
          .
        </Alert>
      ) : null}

      {tab === "pages" && !neverCrawled ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Pages crawled" value={pages.total_pages.toLocaleString()} />
            <Stat label="Indexable" value={pages.indexable_pages.toLocaleString()} />
            <Stat
              label="No editorial links in"
              value={pages.orphaned_pages.toLocaleString()}
              tone={pages.orphaned_pages > 0 ? "warning" : "default"}
            />
            <Stat
              label="In sitemap"
              value={
                pages.sitemap_found
                  ? `${pages.pages_in_sitemap.toLocaleString()} / ${pages.total_pages.toLocaleString()}`
                  : "Not found"
              }
              tone={
                !pages.sitemap_found || pages.pages_in_sitemap < pages.total_pages
                  ? "warning"
                  : "default"
              }
            />
          </div>

          {pages.last_crawl_note ? (
            <p className="mt-2 font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)]">
              {pages.last_crawl_note}
            </p>
          ) : null}

          {!pages.sitemap_found ? (
            <Alert variant="info" className="mt-3">
              No sitemap was found for this site. The crawler reads robots.txt and tries
              the usual locations. If you know where it is, set it in{" "}
              <Link href={clientHref(client.slug, "")} className="font-medium underline">
                Client settings
              </Link>{" "}
              and re-run the crawl — the line above is the last crawl&rsquo;s own summary.
            </Alert>
          ) : null}

          <CrawlFilters
            base={base}
            active={filters}
            matched={pages.matched_pages}
            total={pages.total_pages}
          />

          {detail ? <CrawlPageDetail detail={detail} closeHref={listHref} /> : null}

          <section className="mt-4 workspace-section">
            <SectionHeader
              title="Crawled pages"
              description="In URL order. Click a status, indexability, schema or sitemap cell to filter by it."
              actions={
                <span className="text-xs text-[var(--text-tertiary)]">
                  {pages.items.length.toLocaleString()} shown
                  {pages.truncated ? ` of ${pages.matched_pages.toLocaleString()}` : ""}
                </span>
              }
            />
            <div className="workspace-panel">
              <DataTable
                columns={[
                  {
                    key: "url",
                    header: "Page",
                    render: (row) => (
                      <span
                        className="block max-w-[26rem] truncate font-medium"
                        title={row.title ? `${row.title} — ${row.url}` : row.url}
                      >
                        {pathOf(row.url)}
                      </span>
                    ),
                  },
                  {
                    key: "status_code",
                    header: "Status",
                    align: "right",
                    interactive: true,
                    render: (row) => {
                      const code = row.status_code;
                      if (code === null) return <span className="text-[var(--text-tertiary)]">—</span>;
                      const band = code >= 400 ? "error" : code >= 300 ? "redirect" : "ok";
                      return (
                        <FilterCell base={base} active={filters} param="status" value={band}>
                          <span
                            className={code >= 400 ? "font-semibold text-[var(--danger)]" : ""}
                          >
                            {code}
                          </span>
                        </FilterCell>
                      );
                    },
                  },
                  {
                    key: "indexable",
                    header: "Indexable",
                    interactive: true,
                    render: (row) => (
                      <FilterCell
                        base={base}
                        active={filters}
                        param="indexable"
                        value={row.indexable ? "yes" : "no"}
                      >
                        {row.indexable ? (
                          <span className="badge badge-success">Yes</span>
                        ) : (
                          <span className="badge badge-neutral">No</span>
                        )}
                      </FilterCell>
                    ),
                  },
                  {
                    key: "inbound_editorial_links",
                    header: "Editorial links in",
                    align: "right",
                    render: (row) => (
                      <span
                        className={
                          row.indexable && row.inbound_editorial_links === 0
                            ? "font-semibold text-[var(--warning)]"
                            : ""
                        }
                        title={`${row.inbound_internal_links} including navigation`}
                      >
                        {row.inbound_editorial_links}
                        <span className="ml-1 text-[var(--text-tertiary)]">
                          / {row.inbound_internal_links}
                        </span>
                      </span>
                    ),
                  },
                  {
                    key: "word_count",
                    header: "Words",
                    align: "right",
                    render: (row) => row.word_count.toLocaleString(),
                  },
                  {
                    key: "schema_blocks",
                    header: "Schema",
                    align: "right",
                    interactive: true,
                    render: (row) => (
                      <FilterCell
                        base={base}
                        active={filters}
                        param="schema"
                        value={row.schema_blocks > 0 ? "yes" : "none"}
                      >
                        {row.schema_blocks > 0 ? (
                          row.schema_blocks
                        ) : (
                          <span className="text-[var(--text-tertiary)]">—</span>
                        )}
                      </FilterCell>
                    ),
                  },
                  {
                    key: "in_sitemap",
                    header: "Sitemap",
                    interactive: true,
                    render: (row) => {
                      // Without a sitemap, "missing from it" says nothing — the
                      // finding is the site-level one, not a mark on every row.
                      if (!pages.sitemap_found) {
                        return <span className="text-[var(--text-tertiary)]">No sitemap</span>;
                      }
                      return (
                        <FilterCell
                          base={base}
                          active={filters}
                          param="sitemap"
                          value={row.in_sitemap ? "in" : "missing"}
                        >
                          {row.in_sitemap ? (
                            <span className="badge badge-success">In</span>
                          ) : (
                            <span className="badge badge-warning">Missing</span>
                          )}
                        </FilterCell>
                      );
                    },
                  },
                ]}
                rows={pages.items}
                getRowKey={(row) => row.url}
                rowHref={(row) => detailHref(row.url)}
                rowLabel={(row) => `Open ${row.url}`}
                emptyMessage="No pages match these filters."
              />
            </div>
          </section>
        </>
      ) : null}

      {tab === "schema" && !neverCrawled ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat
              label="Pages described"
              value={`${schema.pages_with_descriptive_schema.toLocaleString()} / ${schema.indexable_pages.toLocaleString()}`}
            />
            <Stat label="Blocks found" value={schema.total_blocks.toLocaleString()} />
            <Stat
              label="Unparseable"
              value={schema.invalid_blocks.toLocaleString()}
              tone={schema.invalid_blocks > 0 ? "warning" : "default"}
            />
            <Stat
              label="Needing attention"
              value={schema.gaps.length.toLocaleString()}
              tone={schema.gaps.length > 0 ? "warning" : "default"}
            />
          </div>

          {schema.types.length > 0 ? (
            <section className="mt-4 workspace-section">
              <SectionHeader
                title="Types present"
                description="What the markup on this site actually declares."
              />
              <div className="workspace-panel">
                <div className="flex flex-wrap gap-2">
                  {schema.types.map((row) => (
                    <span key={row.type} className="badge badge-neutral">
                      {row.type}
                      <span className="ml-1.5 text-[var(--text-tertiary)]">{row.count}</span>
                    </span>
                  ))}
                </div>
              </div>
            </section>
          ) : null}

          <section className="mt-4 workspace-section">
            <SectionHeader
              title="Pages needing structured data"
              description="Unparseable markup first, then pages with none, then pages carrying only the site-wide wrapper a plugin emits."
              actions={
                <span className="text-xs text-[var(--text-tertiary)]">
                  {schema.gaps.length.toLocaleString()} page
                  {schema.gaps.length === 1 ? "" : "s"}
                </span>
              }
            />
            <div className="workspace-panel">
              {schema.gaps.length === 0 ? (
                <Alert variant="success">
                  Every indexable page carries structured data that describes it.
                </Alert>
              ) : (
                <DataTable
                  columns={[
                    {
                      key: "url",
                      header: "Page",
                      render: (row) => (
                        <a
                          href={row.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="block max-w-[26rem] truncate hover:underline"
                          title={row.title ? `${row.title} — ${row.url}` : row.url}
                        >
                          {pathOf(row.url)}
                        </a>
                      ),
                    },
                    {
                      key: "issue",
                      header: "Issue",
                      render: (row) => (
                        <span
                          className={
                            row.issue === "invalid" ? "badge badge-danger" : "badge badge-neutral"
                          }
                        >
                          {ISSUE_LABEL[row.issue] ?? row.issue}
                        </span>
                      ),
                    },
                    {
                      key: "detail",
                      header: "What's there",
                      render: (row) =>
                        row.detail ? (
                          <span
                            className="block max-w-[28rem] truncate text-[var(--text-secondary)]"
                            title={row.detail}
                          >
                            {row.detail}
                          </span>
                        ) : (
                          <span className="text-[var(--text-tertiary)]">Nothing</span>
                        ),
                    },
                  ]}
                  rows={schema.gaps}
                  getRowKey={(row) => row.url}
                  emptyMessage="Nothing to fix."
                />
              )}
            </div>
          </section>
        </>
      ) : null}
    </section>
  );
}
