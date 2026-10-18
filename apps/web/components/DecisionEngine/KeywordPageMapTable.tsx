"use client";

import { useRouter } from "next/navigation";
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
  /** primary | secondary | null. Null means nobody has said. */
  term_role: "primary" | "secondary" | null;
  group_name: string | null;
  priority: boolean;
  source: string | null;
  volume: number | null;
  difficulty: number | null;
  current_position: number | null;
  suggested_target_url: string | null;
  /** Which read it came from: where the site ranks, or what a page is about. */
  suggested_from?: "search_console" | "subject" | null;
  suggested_margin?: number | null;
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
/**
 * The site's own origin, taken from the pages the crawl found.
 *
 * Every row on this table points at the same domain, so showing it in every
 * field spends two dozen characters saying the one thing that is never in
 * question — and truncates the part that is. Half a dozen capabilities
 * pages all read "https://smamarketing.com/capabilities" and there is no
 * way to tell which is which.
 */
function siteOrigin(pages: string[]): string | null {
  for (const page of pages) {
    try {
      return new URL(page).origin;
    } catch {
      continue;
    }
  }
  return null;
}

/** What goes in the box: a path on this site, a whole URL anywhere else. */
function forDisplay(url: string, origin: string | null): string {
  if (!origin || !url.startsWith(`${origin}/`)) return url;
  return url.slice(origin.length) || "/";
}

/** What gets saved: a path typed here belongs to this site. */
function forSaving(value: string, origin: string | null): string {
  const text = value.trim();
  if (!origin || !text.startsWith("/")) return text;
  return `${origin}${text}`;
}

/** A column header that orders the table. */
function SortHeader({
  column,
  children,
  align,
  sortKey,
  sortDir,
  onSort,
}: {
  column: SortKey;
  children: React.ReactNode;
  align?: "right";
  sortKey: SortKey;
  sortDir: "asc" | "desc";
  onSort: (key: SortKey) => void;
}) {
  const active = sortKey === column;
  return (
    <th className={align === "right" ? "text-right" : undefined}
        aria-sort={active ? (sortDir === "asc" ? "ascending" : "descending") : undefined}>
      <button
        type="button"
        onClick={() => onSort(column)}
        className="inline-flex items-center gap-1 hover:text-[var(--text-primary)]"
      >
        {children}
        <span aria-hidden className="text-[9px] leading-none">
          {active ? (sortDir === "asc" ? "▲" : "▼") : "⇅"}
        </span>
      </button>
    </th>
  );
}

type SortKey =
  | "priority"
  | "keyword"
  | "volume"
  | "difficulty"
  | "position"
  | "role"
  | "page"
  | "status";

/** What each column orders by — the value, not the control that shows it. */
const SORTERS: Record<SortKey, (row: KeywordMapRow) => number | string | null> = {
  priority: (row) => (row.priority ? 1 : 0),
  keyword: (row) => row.keyword.toLowerCase(),
  volume: (row) => row.volume,
  difficulty: (row) => row.difficulty,
  // Not ranking sorts last rather than first: 0 would read as the best
  // position on the site.
  position: (row) => row.current_position,
  role: (row) => row.term_role ?? "",
  page: (row) => (row.target_url ?? "").toLowerCase(),
  status: (row) => (row.mapped ? 1 : 0),
};

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
  origin: string | null;
}) {
  // Held as it is shown — a path for this site — and expanded on save.
  const [pageUrl, setPageUrl] = useState(forDisplay(row.target_url ?? "", origin));
  const [role, setRole] = useState(row.term_role ?? "");
  const [priority, setPriority] = useState(row.priority);
  const [saved, setSaved] = useState<"idle" | "ok" | "error">("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const dirty =
    (row.target_url ?? "") !== forSaving(pageUrl, origin) ||
    (row.term_role ?? "") !== role ||
    row.priority !== priority;

  function save(next?: { url?: string; role?: string; priority?: boolean }) {
    const data = new FormData();
    data.set("clientId", clientId);
    data.set("clientSlug", clientSlug);
    data.set("keyword", row.keyword);
    data.set("target_url", next?.url ?? forSaving(pageUrl, origin));
    data.set("term_role", next?.role ?? role);
    data.set("priority", String(next?.priority ?? priority));
    // The group is SE Ranking's, not a judgement, and it rides along so a
    // term keeps its group if the fact row is ever re-synced under it.
    data.set("group_name", row.group_name ?? "");
    startTransition(async () => {
      const result = await saveKeywordPageMapAction(data);
      setSaved(result.ok ? "ok" : "error");
      setMessage(result.ok ? null : result.error);
    });
  }

  return (
    <tr className="align-top">
      <td className="font-medium">
        <div className="flex items-start gap-2">
          {/* V1 reads "priority-group keywords". Nothing marked one before,
              so the test could not run for any client. One click. */}
          <input
            type="checkbox"
            checked={priority}
            onChange={(event) => {
              setPriority(event.target.checked);
              setSaved("idle");
              save({ priority: event.target.checked });
            }}
            aria-label={`Mark ${row.keyword} a priority term`}
            title={
              priority
                ? "Counted in the visibility test. Untick to leave it out."
                : "Tick to count this term in the visibility test."
            }
            className="mt-1 h-4 w-4 flex-none"
          />
          <span>
            {row.keyword}
            {row.group_name ? (
              <span className="mt-0.5 block text-xs font-normal text-[var(--text-tertiary)]">
                {row.group_name}
              </span>
            ) : null}
          </span>
        </div>
      </td>
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
      <td className="whitespace-nowrap">
        {/* A primary term earns a title rewrite; a secondary one earns a
            section. Blank is its own answer and stays available — a rule
            that wants a primary has to tell "nobody said" from "secondary". */}
        <select
          value={role}
          onChange={(event) => {
            setRole(event.target.value);
            setSaved("idle");
            save({ role: event.target.value });
          }}
          aria-label={`Role for ${row.keyword}`}
          className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
        >
          {/* It decides what the engine asks for: the title for a primary
              term, a section of its own for a secondary one. */}
          <option value="">Not set — no role assumed</option>
          <option value="primary">Primary — owns the title</option>
          <option value="secondary">Secondary — earns a section</option>
        </select>
      </td>
      <td className="min-w-[30rem]">
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
            // The whole URL on hover, for a path that still runs long.
            title={forSaving(pageUrl, origin) || undefined}
            className="flex-1 font-[family-name:var(--font-mono)] text-[12.5px]"
          />
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={pending || (!dirty && row.mapped)}
            onClick={() => save({ url: pageUrl })}
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
              setPageUrl(forDisplay(row.suggested_target_url ?? "", origin));
              setSaved("idle");
            }}
          >
            {/* The two reads mean different things and a person deciding
                should know which they are looking at: one is where the site
                ranks today, the other is what a page is about. */}
            {row.suggested_from === "subject" ? (
              <>
                Closest page by subject: {forDisplay(row.suggested_target_url ?? "", origin)}
                {" "}— use this. Nothing ranks for this term yet.
              </>
            ) : row.suggested_instead_of ? (
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
            {row.target_url ? row.source === "auto" ? "Auto-mapped" : "Your mapping" : "No page, recorded"}
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
  const router = useRouter();
  const [matching, startMatching] = useTransition();
  const [matchNote, setMatchNote] = useState<string | null>(null);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [onlyUnmapped, setOnlyUnmapped] = useState(true);
  const [onlyPriority, setOnlyPriority] = useState(false);
  const [group, setGroup] = useState("");
  // Volume first: the question this table is usually opened with is "what
  // are the biggest terms nobody has mapped yet".
  const [sortKey, setSortKey] = useState<SortKey>("volume");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const origin = useMemo(() => siteOrigin(pages), [pages]);
  const sortProps = {
    sortKey,
    sortDir,
    onSort: (key: SortKey) => {
      // Turn the column you are on around; open a new one the way it
      // reads best — biggest first for a number, A–Z for a name.
      if (key === sortKey) {
        setSortDir(sortDir === "desc" ? "asc" : "desc");
        return;
      }
      setSortKey(key);
      setSortDir(
        key === "keyword" || key === "page" || key === "role" || key === "position"
          ? "asc"
          : "desc",
      );
    },
  };

  const groups = useMemo(
    () => [...new Set(rows.map((r) => r.group_name).filter(Boolean))].sort() as string[],
    [rows],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return rows.filter((row) => {
      if (onlyUnmapped && row.mapped) return false;
      if (onlyPriority && !row.priority) return false;
      if (group && row.group_name !== group) return false;
      if (!needle) return true;
      return (
        row.keyword.toLowerCase().includes(needle) ||
        (row.target_url ?? "").toLowerCase().includes(needle)
      );
    });
  }, [rows, query, onlyUnmapped, onlyPriority, group]);

  const sorted = useMemo(() => {
    const read = SORTERS[sortKey];
    const direction = sortDir === "asc" ? 1 : -1;
    return [...visible].sort((a, b) => {
      const left = read(a);
      const right = read(b);
      // A term with no volume or no position is never the answer to "show
      // me the biggest" or "show me the closest", so it sinks either way.
      // Two of them are a tie, and a tie is broken below rather than left
      // to the order they arrived in.
      if (left !== null || right !== null) {
        if (left === null) return 1;
        if (right === null) return -1;
        const by =
          typeof left === "number" && typeof right === "number"
            ? (left - right) * direction
            : String(left).localeCompare(String(right)) * direction;
        if (by !== 0) return by;
      }
      // Every tie ends A–Z, so the order does not depend on anything that
      // changes when a row is saved. The server sends mapped terms last:
      // without this, saving a term on a client with no search volume —
      // where every row ties — dropped it to the bottom of the table the
      // moment it was saved, which reads as the save doing nothing.
      return a.keyword.localeCompare(b.keyword);
    });
  }, [visible, sortKey, sortDir]);

  const unmapped = rows.filter((row) => !row.mapped).length;
  const priorityCount = rows.filter((row) => row.priority).length;

  /**
   * Read the site and propose a page for every unmapped term.
   *
   * It runs while you wait rather than in the background, because the thing
   * you do next is read what it proposed. A large site takes tens of
   * seconds: it embeds every crawled page once, then every term.
   */
  function suggestPages() {
    setMatchError(null);
    setMatchNote(null);
    startMatching(async () => {
      const res = await fetch("/api/proxy/keyword-suggestions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clientId }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setMatchError(body.detail || "The matcher did not finish");
        return;
      }
      if (body.reason) {
        setMatchError(body.reason);
        return;
      }
      // Say what it did not propose as well as what it did: a term with no
      // page close enough to name is the finding, not an omission.
      setMatchNote(body.map
        ? `Built ${body.map.mapped} automatic mappings. Preserved ${body.map.preserved} user decisions. ${body.map.gaps} gaps and ${body.map.conflicts} conflicting matches need review.`
        : `Read ${body.pages} pages and generated ${body.stored} suggestions.`);
      router.refresh();
    });
  }

  return (
    <section className="workspace-section">
      <SectionHeader
        title="Keyword to page map"
        description="The tool builds page ownership from page topics and observed search evidence. Review the gaps or override a match. Your saved decisions are preserved when the map is rebuilt."
        actions={
          <div className="flex items-center gap-3">
            <span className="text-xs text-[var(--text-tertiary)]">
              {rows.length - unmapped} of {rows.length} mapped · {priorityCount}{" "}
              priority
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={suggestPages}
              disabled={matching}
            >
              {matching ? "Reading the site…" : "Build / refresh map"}
            </button>
          </div>
        }
      />

      {matchError ? (
        <p className="mb-3 text-sm text-[var(--danger)]">{matchError}</p>
      ) : null}
      {matchNote ? (
        <p className="mb-3 text-sm text-[var(--text-secondary)]">{matchNote}</p>
      ) : null}

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
          Gaps only{unmapped > 0 ? ` (${unmapped})` : ""}
        </label>
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={onlyPriority}
            onChange={(event) => setOnlyPriority(event.target.checked)}
          />
          Priority only ({priorityCount})
        </label>
        {/* The groups come from SE Ranking already. Working through one at a
            time is how ten priority terms get marked without reading 73. */}
        {groups.length > 1 ? (
          <select
            value={group}
            onChange={(event) => setGroup(event.target.value)}
            aria-label="Filter by keyword group"
            className="min-h-[36px] rounded-lg border border-[var(--border)] bg-[var(--surface)] px-2 text-sm"
          >
            <option value="">All groups</option>
            {groups.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        ) : null}
      </div>

      {/* A tick in a column headed "Priority" says nothing about what it
          does. The visibility test reads exactly these terms, and that is
          the only reason to tick one. */}
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        <strong className="text-[var(--text-primary)]">Priority</strong> is the
        set the visibility test judges: it asks how many of these reach the top
        ten. Tick the terms you are trying to win — {priorityCount} ticked
        {priorityCount === 0 ? ", so the test cannot run" : ""}. Everything else
        stays tracked and mappable.
      </p>

      {/* Shared by every row's input, so the browser offers real pages
          instead of leaving someone to type a URL from memory. */}
      <datalist id="keyword-map-pages">
        {pages.map((page) => (
          <option key={page} value={forDisplay(page, origin)} />
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
                <SortHeader column="keyword" {...sortProps}>
                  Keyword
                </SortHeader>
                <SortHeader column="volume" align="right" {...sortProps}>
                  Volume
                </SortHeader>
                <SortHeader column="difficulty" align="right" {...sortProps}>
                  Difficulty
                </SortHeader>
                <SortHeader column="position" align="right" {...sortProps}>
                  Position
                </SortHeader>
                <SortHeader column="role" {...sortProps}>
                  Role
                </SortHeader>
                <SortHeader column="page" {...sortProps}>
                  Page that owns it
                </SortHeader>
                <SortHeader column="status" {...sortProps}>
                  Status
                </SortHeader>
              </tr>
            </thead>
            <tbody>
              {sorted.map((row) => (
                <Row
                  key={row.keyword}
                  row={row}
                  pages={pages}
                  origin={origin}
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
        preserves your decision for content planning; rebuilding the map will not replace it.
      </p>
    </section>
  );
}
