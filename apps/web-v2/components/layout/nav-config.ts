import { BarChart3, Eye, FileText, Target, type LucideIcon } from "lucide-react";

export type NavItem = { label: string; path: string };
export type NavGroup = { title: string; icon: LucideIcon; items: NavItem[] };

/** The order Ryan set: what each group answers. */
export const GROUPS: NavGroup[] = [
  {
    title: "Organic IQ analytics",
    icon: BarChart3,
    items: [
      { label: "Monthly review", path: "/review" },
      { label: "Business Intelligence", path: "/bi" },
      { label: "Decision engine", path: "/engine" },
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
      { label: "Schema & knowledge graph", path: "/schema" },
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
      { label: "Content calendar", path: "/content-calendar" },
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
