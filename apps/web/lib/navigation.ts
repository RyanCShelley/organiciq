import { accountToolHref } from "@/lib/account-routes";

export type NavItem = {
  href: string;
  label: string;
  exact?: boolean;
  /** Query string appended by withNavContext (e.g. Watch List AI tab). */
  tab?: string;
};

export type NavGroup = {
  label: string;
  items: NavItem[];
};

export function accountNavGroups(clientSlug: string): NavGroup[] {
  const settingsHref = clientSlug ? `/clients/${clientSlug}` : "/clients";
  const tool = (path: string) => (clientSlug ? accountToolHref(clientSlug, path) : `/${path}`);
  return [
    {
      label: "Account",
      items: [
        { href: tool("dashboard"), label: "Dashboard", exact: true },
        { href: tool("watch-list"), label: "Watch List" },
        { href: tool("content-opp"), label: "Content Opp" },
        { href: tool("decision-engine"), label: "Decision Engine" },
        { href: tool("annotations"), label: "Annotations" },
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

export function isNavActive(pathname: string, href: string, exact = false): boolean {
  if (exact) return pathname === href;
  return pathname === href || pathname.startsWith(`${href}/`);
}

function pathEncodesClient(href: string): boolean {
  if (href.startsWith("/clients/")) return true;
  // /{slug}/dashboard|watch-list|…
  const parts = href.split("/").filter(Boolean);
  if (parts.length >= 2) {
    const tool = parts[1];
    return ["dashboard", "watch-list", "content-opp", "decision-engine", "annotations"].includes(
      tool,
    );
  }
  return false;
}

export function withNavContext(
  href: string,
  clientId: string,
  from: string,
  to: string,
  extra?: { tab?: string },
): string {
  const params = new URLSearchParams();
  // Client is already in the path for workspace + account-tool URLs.
  if (clientId && !pathEncodesClient(href)) {
    params.set("clientId", clientId);
  }
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  if (extra?.tab) params.set("tab", extra.tab);
  const qs = params.toString();
  return qs ? `${href}?${qs}` : href;
}
