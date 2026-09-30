import Link from "next/link";

import { Alert } from "@/components/ui/Alert";
import type { CrawlLinkRow, CrawlPageDetail as Detail } from "@/lib/api";

/**
 * One crawled page in detail: what links to it, what it links to, and the
 * structured data as served.
 *
 * Both the link graph and the raw schema blocks were already stored and
 * entirely invisible — a count told you a page was under-linked without saying
 * by whom, and "no descriptive schema" without showing what was actually there.
 */

function pathOf(url: string): string {
  try {
    const { pathname, search } = new URL(url);
    return `${pathname}${search}` || "/";
  } catch {
    return url;
  }
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-[0.06em] text-[var(--text-tertiary)]">
        {label}
      </div>
      <div className="mt-0.5 text-[13px] text-[var(--text-secondary)]">{children}</div>
    </div>
  );
}

function LinkList({
  rows,
  direction,
  emptyMessage,
}: {
  rows: CrawlLinkRow[];
  direction: "from" | "to";
  emptyMessage: string;
}) {
  if (rows.length === 0) {
    return <p className="text-[12.5px] text-[var(--text-tertiary)]">{emptyMessage}</p>;
  }
  return (
    <ul className="space-y-1.5">
      {rows.map((row) => (
        <li key={`${direction}-${row.url}`} className="flex flex-wrap items-baseline gap-x-2">
          <a
            href={row.url}
            target="_blank"
            rel="noopener noreferrer"
            className="max-w-[24rem] truncate text-[12.5px] hover:underline"
            title={row.url}
          >
            {pathOf(row.url)}
          </a>
          {row.anchor_text ? (
            <span
              className="max-w-[18rem] truncate text-[12px] text-[var(--text-tertiary)]"
              title={row.anchor_text}
            >
              &ldquo;{row.anchor_text}&rdquo;
            </span>
          ) : null}
          {row.occurrences > 1 ? (
            <span className="text-[11.5px] text-[var(--text-tertiary)]">×{row.occurrences}</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

export function CrawlPageDetail({ detail, closeHref }: { detail: Detail; closeHref: string }) {
  if (!detail.found) {
    return (
      <Alert variant="info" className="mt-4">
        That page isn&rsquo;t in the latest crawl.{" "}
        <Link href={closeHref} className="font-medium underline">
          Back to all pages
        </Link>
      </Alert>
    );
  }

  // The API sends editorial links in full and template links as a count: a
  // page's nav and footer are the same on every page, so the only thing worth
  // knowing is that it is in them.
  const inbound = detail.inbound ?? [];
  const outbound = detail.outbound ?? [];
  const blocks = detail.schema_blocks ?? [];
  const templateIn = detail.inbound_template_links ?? 0;
  const templateOut = detail.outbound_template_links ?? 0;

  return (
    <section className="card mt-4 p-[var(--card-padding)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="font-[family-name:var(--font-display)] text-[15px] font-extrabold text-[var(--text-primary)]">
            {detail.title || pathOf(detail.url)}
          </h3>
          <a
            href={detail.raw_url || detail.url}
            target="_blank"
            rel="noopener noreferrer"
            className="mt-1 block max-w-[46rem] truncate font-[family-name:var(--font-mono)] text-[11.5px] text-[var(--text-tertiary)] hover:underline"
          >
            {detail.url}
          </a>
        </div>
        <Link href={closeHref} className="btn btn-secondary shrink-0">
          Close
        </Link>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Field label="Status">
          {detail.status_code ?? "—"}
          {detail.indexable ? null : (
            <span className="ml-2 badge badge-neutral">not indexable</span>
          )}
        </Field>
        <Field label="Words">{(detail.word_count ?? 0).toLocaleString()}</Field>
        <Field label="Editorial links in">
          <span className={inbound.length === 0 ? "text-[var(--warning)] font-semibold" : ""}>
            {inbound.length}
          </span>
          {templateIn > 0 ? (
            <span className="text-[var(--text-tertiary)]"> + {templateIn} from templates</span>
          ) : null}
        </Field>
        <Field label="Sitemap">
          {detail.in_sitemap ? "Included" : <span className="text-[var(--warning)]">Missing</span>}
        </Field>
      </div>

      {detail.canonical_url && detail.canonical_url !== detail.url ? (
        <Alert variant="info" className="mt-3">
          Canonical points elsewhere:{" "}
          <span className="font-[family-name:var(--font-mono)] text-[12px]">
            {detail.canonical_url}
          </span>
        </Alert>
      ) : null}

      <div className="mt-5 grid gap-5 lg:grid-cols-2">
        <div className="min-w-0">
          <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            Pages linking here ({inbound.length} editorial)
          </h4>
          {templateIn > 0 ? (
            <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">
              Plus {templateIn.toLocaleString()} template link
              {templateIn === 1 ? "" : "s"} — it sits in the navigation or footer.
            </p>
          ) : null}
          <div className="mt-2">
            <LinkList
              rows={inbound}
              direction="from"
              emptyMessage="Nothing links to this page editorially."
            />
          </div>
        </div>
        <div className="min-w-0">
          <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
            Links from this page ({outbound.length} editorial)
          </h4>
          {templateOut > 0 ? (
            <p className="mt-1 text-[12px] text-[var(--text-tertiary)]">
              Plus {templateOut.toLocaleString()} template link
              {templateOut === 1 ? "" : "s"} from its navigation and footer.
            </p>
          ) : null}
          <div className="mt-2">
            <LinkList
              rows={outbound}
              direction="to"
              emptyMessage="This page has no editorial links out."
            />
          </div>
        </div>
      </div>

      <div className="mt-5">
        <h4 className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--text-tertiary)]">
          Structured data ({blocks.length} block{blocks.length === 1 ? "" : "s"})
        </h4>
        {blocks.length === 0 ? (
          <p className="mt-2 text-[12.5px] text-[var(--text-tertiary)]">
            No structured data on this page.
          </p>
        ) : (
          <div className="mt-2 space-y-2">
            {blocks.map((block, index) => (
              <details
                key={`${block.syntax}-${block.schema_type ?? "none"}-${index}`}
                className="rounded-[10px] border border-[var(--border)] bg-[var(--surface-muted)]"
              >
                <summary className="cursor-pointer list-none px-3 py-2 text-[12.5px]">
                  <span className="font-semibold text-[var(--text-primary)]">
                    {block.schema_type ?? "No @type"}
                  </span>
                  <span className="ml-2 text-[var(--text-tertiary)]">{block.syntax}</span>
                  {block.parse_error ? (
                    <span className="ml-2 badge badge-danger">{block.parse_error}</span>
                  ) : null}
                </summary>
                <pre className="max-h-[22rem] overflow-auto border-t border-[var(--border)] px-3 py-2 font-[family-name:var(--font-mono)] text-[11.5px] leading-relaxed text-[var(--text-secondary)]">
                  {block.raw
                    ? JSON.stringify(block.raw, null, 2)
                    : block.raw_text || "(nothing recorded)"}
                </pre>
              </details>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
