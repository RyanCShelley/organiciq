import { BarChart3, Briefcase, Eye, FileText, Target, type LucideIcon } from "lucide-react";

export type NavItem = {
  label: string;
  path: string;
  /** Shown only for clients on Ads Accelerator. */
  ads?: boolean;
  /** Left out for consulting clients: the work it plans is done by their own team. */
  execution?: boolean;
};
export type NavGroup = { title: string; icon: LucideIcon; items: NavItem[]; /** Shown only for consulting clients. */ consulting?: boolean };

/** The order Ryan set: what each group answers. */
export const GROUPS: NavGroup[] = [
  {
    title: "Consulting",
    icon: Briefcase,
    consulting: true,
    items: [{ label: "Workspace", path: "/consulting" }],
  },
  {
    title: "Analytics",
    icon: BarChart3,
    items: [
      { label: "Monthly review", path: "/review" },
      { label: "OrganicIQ insights", path: "/bi" },
      { label: "Ads Accelerator", path: "/ads", ads: true },
      { label: "Decision engine", path: "/engine" },
      { label: "Annotations", path: "/annotations" },
    ],
  },
  {
    title: "Visibility",
    icon: Eye,
    items: [
      { label: "Search visibility", path: "/search-visibility" },
      { label: "LLM visibility", path: "/llm" },
    ],
  },
  {
    title: "Dual optimization",
    icon: Target,
    items: [
      { label: "Site health", path: "/site-health" },
      { label: "Machine readability", path: "/schema" },
      { label: "CTR optimizer", path: "/ctr" },
      { label: "Inlink suggester", path: "/inlinks" },
    ],
  },
  {
    title: "Content engine",
    icon: FileText,
    items: [
      { label: "Content gaps", path: "/content-gaps" },
      { label: "Content refreshes", path: "/content-refreshes" },
      { label: "Content optimizer", path: "/content-optimizer" },
      { label: "Content calendar", path: "/content-calendar", execution: true },
    ],
  },
];

/** Settings holds the watchlist, so its page counts as being in Settings. */
export const SETTINGS_PATHS = ["/settings", "/watchlist"];

/** Where a path sits, for the top bar: the group and page names. */
export function locate(pathname: string, clientSlug: string | undefined): { group: string | null; page: string | null } {
  if (pathname.startsWith("/admin")) return { group: null, page: "Admin" };
  if (!clientSlug) return { group: null, page: null };
  const rest = pathname.slice(`/${clientSlug}`.length);
  if (SETTINGS_PATHS.some((p) => rest.startsWith(p))) return { group: null, page: "Client settings" };
  for (const g of GROUPS) {
    const item = g.items.find((i) => rest.startsWith(i.path));
    if (item) return { group: g.title, page: item.label };
  }
  return { group: null, page: null };
}

/** Starter questions for the Ask panel, by page. Free: no model is asked until one is chosen. */
export const SUGGESTIONS: Record<string, string[]> = {
  "/review": ["Why did orders and revenue move this month?", "What should we do first in the next month?", "Write a short summary of this month for the client"],
  "/ads": ["Which ad group costs the most per click?", "Which markets and devices bring the clicks?"],
  "/bi": ["Which channel drove the change?", "Compare this period with the same period last year", "Explain what these charts show in plain words"],
  "/engine": ["Which task would move the most traffic?", "What did we ship, and did it work?", "Why is the first action on the list?"],
  "/search-visibility": ["Which terms moved the most?", "Where are we close to page one?", "Which terms are we losing?"],
  "/llm": ["Where do AI platforms name the brand?", "Which competitors are named instead of us?", "What would get us cited more?"],
  "/site-health": ["What should we fix first?", "Which issues affect the most pages?", "Explain these issues for the client"],
  "/schema": ["Which pages are missing structured data?", "What should we add first?", "Explain this for the client"],
  "/content-optimizer": ["Which pages need only a small change instead of a refresh?", "What questions should this page's FAQ answer?"],
  "/ctr": ["Which page has the most to gain from a better title?", "Why is this page's click-through low?"],
  "/inlinks": ["Which page needs links most?", "Where should we link to the top page from?"],
  "/content-gaps": ["Which gap should we write first?", "Why is this a gap?", "What topics are we missing?"],
  "/content-refreshes": ["Why did the top page lose traffic?", "Which pages compete with each other?", "What should we refresh first?"],
  "/content-calendar": ["What is overdue?", "What is planned for next month?"],
};

export function suggestionsFor(pathname: string, clientSlug: string | undefined): string[] | undefined {
  if (!clientSlug) return undefined;
  const rest = pathname.slice(`/${clientSlug}`.length);
  const key = Object.keys(SUGGESTIONS).find((k) => rest.startsWith(k));
  return key ? SUGGESTIONS[key] : undefined;
}
