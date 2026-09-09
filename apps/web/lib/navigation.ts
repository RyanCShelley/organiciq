export type NavItem = {
  href: string;
  label: string;
  exact?: boolean;
  /** Query string appended by withNavContext (e.g. Watch List Content Opp tab). */
  tab?: string;
  /** When true, active only when tab is this value. When false/undefined on /watch-list, active unless Content Opp. */
  contentOpp?: boolean;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export function accountNavGroups(clientSlug: string): NavGroup[] {
  const settingsHref = clientSlug ? `/clients/${clientSlug}` : "/clients";
  return [
    {
      label: "Account",
      items: [
        { href: "/dashboard", label: "Dashboard", exact: true },
        { href: "/watch-list", label: "Watch List" },
        { href: "/watch-list", label: "Content Opp", tab: "content-opp", contentOpp: true },
        { href: "/decision-engine", label: "Decision Engine" },
        { href: "/annotations", label: "Annotations" },
        { href: settingsHref, label: "Client settings" },
      ],
    },
  ];
}

export const PLATFORM_NAV_ITEMS: NavItem[] = [
  { href: "/clients", label: "All clients", exact: true },
  { href: "/platform", label: "Overview", exact: true },
  { href: "/platform/data-health", label: "Data health" },
  { href: "/platform/jobs", label: "Sync jobs" },
  { href: "/platform/settings", label: "Settings" },
];

/** Platform surfaces: hide client switcher + Account nav (All clients + /platform/*). */
export function isPlatformContext(pathname: string): boolean {
  if (pathname === "/clients") return true;
  if (pathname.startsWith("/platform")) return true;
  if (pathname.startsWith("/admin")) return true;
  return false;
}

export function isNavActive(
  pathname: string,
  href: string,
  exact = false,
  options?: { tab?: string | null; contentOpp?: boolean },
): boolean {
  if (href === "/watch-list" || options?.contentOpp) {
    if (!pathname.startsWith("/watch-list")) return false;
    const isContentOpp = options?.tab === "content-opp";
    if (options?.contentOpp) return isContentOpp;
    return !isContentOpp;
  }
  if (href === "/dashboard" || exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function withNavContext(
  href: string,
  clientId: string,
  from: string,
  to: string,
  extra?: { tab?: string },
): string {
  const params = new URLSearchParams();
  // Client workspace paths already encode the client; skip redundant clientId query.
  if (clientId && !href.startsWith("/clients/")) {
    params.set("clientId", clientId);
  }
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  if (extra?.tab) params.set("tab", extra.tab);
  const qs = params.toString();
  return qs ? `${href}?${qs}` : href;
}
