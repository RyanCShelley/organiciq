"use client";

import { useMemo, useState, useTransition } from "react";

import { saveKeywordPageMapAction } from "@/app/(app)/keyword-map-actions";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { SectionHeader } from "@/components/ui/SectionHeader";

export type KeywordMapRow = {
  keyword: string;
  target_url: string | null;
  note: string | null;
  mapped: boolean;
  volume: number | null;
  difficulty: number | null;
  current_position: number | null;
  suggested_target_url: string | null;
  suggested_impressions: number | null;
  suggested_instead_of: string | null;
};

function formatNum(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString();
}

/**
 * One row's editor.
 *
 * Saved per keyword rather than behind one Save button for the page: the
 * work is done a term at a time, and a form that loses half of it on a
 * reload is a form that stays empty.
 */
function Row({
  row,
  clientId,
  clientSlug,
  pages,
}: {
  row: KeywordMapRow;
  clientId: string;
  clientSlug: string;
  pages: string[];
}) {
  const [pageUrl, setPageUrl] = useState(row.target_url ?? "");
  const [saved, setSaved] = useState<"idle" | "ok" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const dirty = (row.target_url ?? "") !== pageUrl;

  function save(nextUrl: string) {
    const data = new FormData();
    data.set("clientId", clientId);
    data.set("clientSlug", clientSlug);
    data.set("keyword", row.keyword);
    data.set("target_url", nextUrl);
    startTransition(async () => {
      const result = await saveKeywordPageMapAction(data);
      setSaved(result.ok ? "ok" : "error");
      setMessage(result.ok ? null : result.error);
    });
  }

  return (
    <tr className="align-top">
      <td className="whitespace-nowrap font-medium">{row.keyword}</td>
      <td className="whitespace-nowrap text-right tabular-nums">
        {formatNum(row.volume)}
      </td>
      <td className="whitespace-nowrap text-right tabular-nums">
        {row.difficulty === null ? "—" : Math.round(row.difficulty)}
      </td>
      <td className="whitespace-nowrap text-right tabular-nums">
        {row.current_position === null ? (
          <span className="text-[var(--text-tertiary)]">not ranking</span>
        ) : (
          Math.round(row.current_position)
        )}
      </td>
      <td className="min-w-[22rem]">
        <div className="flex items-center gap-2">
          <Input
            list="keyword-map-pages"
            value={pageUrl}
            onChange={(event) => {
              setPageUrl(event.target.value);
              setSaved("idle");
            }}
            placeholder="No page owns this yet"
            aria-label={`Page for ${row.keyword}`}
            className="flex-1"
          />
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={pending || (!dirty && row.mapped)}
            onClick={() => save(pageUrl)}
          >
            {pending ? "Saving…" : row.mapped && !dirty ? "Saved" : "Save"}
          </button>
        </div>
        {/* What the engine would otherwise guess, so the decision is a
            confirmation rather than research. */}
        {!row.mapped && row.suggested_target_url ? (
          <button
            type="button"
            className="mt-1 text-left text-xs text-[var(--brand-teal-hover)] hover:underline"
            onClick={() => {
              setPageUrl(row.suggested_target_url ?? "");
              setSaved("idle");
            }}
          >
            {row.suggested_instead_of ? (
              <>
                Search Console shows {row.suggested_instead_of} (
                {formatNum(row.suggested_impressions)} impressions), which
                canonicalises to {row.suggested_target_url} — use the canonical
              </>
            ) : (
              <>
                Search Console shows {row.suggested_target_url} (
                {formatNum(row.suggested_impressions)} impressions) — use this
              </>
            )}
          </button>
        ) : null}
        {saved === "error" && message ? (
          <div className="mt-1 text-xs text-[var(--danger)]">{message}</div>
        ) : null}
        {saved === "ok" ? (
          <div className="mt-1 text-xs text-[var(--success)]">Saved.</div>
        ) : null}
      </td>
      <td className="whitespace-nowrap">
        {row.mapped ? (
          <Badge variant={row.target_url ? "success" : "neutral"}>
            {row.target_url ? "Mapped" : "No page, recorded"}
          </Badge>
        ) : (
          <Badge variant="warning">Unmapped</Badge>
        )}
      </td>
    </tr>
  );
}

export function KeywordPageMapTable({
  rows,
  pages,
  clientId,
  clientSlug,
}: {
  rows: KeywordMapRow[];
  pages: string[];
  clientId: string;
  clientSlug: string;
}) {
  const [query, setQuery] = useState("");
  const [onlyUnmapped, setOnlyUnmapped] = useState(false);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (onlyUnmapped && row.mapped) return false;
      if (!needle) return true;
      return (
        row.keyword.toLowerCase().includes(needle) ||
        (row.target_url ?? "").toLowerCase().includes(needle)
      );
    });
  }, [rows, query, onlyUnmapped]);

  const unmapped = rows.filter((row) => !row.mapped).length;

  return (
    <section className="workspace-section">
      <SectionHeader
        title="Keyword to page map"
        description="Which page is meant to own each term. The engine asks for this on every ranking finding, because Search Console reports where Google currently shows a page — which on a term you do not rank for is either nothing or the wrong page."
        actions={
          <span className="text-xs text-[var(--text-tertiary)]">
            {rows.length - unmapped} of {rows.length} mapped
          </span>
        }
      />

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <div className="max-w-md flex-1">
          <Input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search keywords or pages…"
            aria-label="Search the keyword map"
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={onlyUnmapped}
            onChange={(event) => setOnlyUnmapped(event.target.checked)}
          />
          Unmapped only{unmapped > 0 ? ` (${unmapped})` : ""}
        </label>
      </div>

      {/* Shared by every row's input, so the browser offers real pages
          instead of leaving someone to type a URL from memory. */}
      <datalist id="keyword-map-pages">
        {pages.map((page) => (
          <option key={page} value={page} />
        ))}
      </datalist>

      {visible.length === 0 ? (
        <p className="text-sm text-[var(--text-secondary)]">
          {rows.length === 0
            ? "No tracked keywords yet. Add them to the watchlist and they appear here."
            : "Nothing matches that filter."}
        </p>
      ) : (
        <div className="table-shell overflow-x-auto">
          <table>
            <thead>
              <tr>
                <th>Keyword</th>
                <th className="text-right">Volume</th>
                <th className="text-right">Difficulty</th>
                <th className="text-right">Position</th>
                <th>Page that owns it</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <Row
                  key={row.keyword}
                  row={row}
                  pages={pages}
                  clientId={clientId}
                  clientSlug={clientSlug}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="mt-3 text-xs text-[var(--text-tertiary)]">
        Leaving a page blank and saving records “no page owns this yet”. That
        is an answer: the engine stops asking and prescribes writing one.
      </p>
    </section>
  );
}
