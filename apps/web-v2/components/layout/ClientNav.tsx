"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

type Item = { label: string; path: string; soon?: boolean };

/** The order Ryan set: what each group answers, and what is still to be built (greyed, not linked). */
const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: "OrganicIQ Analytics",
    items: [
      { label: "Monthly review", path: "/review" },
      { label: "Business Intelligence", path: "/bi" },
      { label: "Decision engine", path: "/engine" },
    ],
  },
  {
    title: "Visibility",
    items: [
      { label: "Search visibility", path: "/search-visibility" },
      { label: "LLM visibility", path: "/llm" },
    ],
  },
  {
    title: "Dual optimization",
    items: [
      { label: "Site health", path: "/site-health" },
      { label: "Schema & knowledge graph", path: "/schema" },
      { label: "CTR optimizer", path: "/ctr", soon: true },
      { label: "Inlink suggester", path: "/inlinks", soon: true },
    ],
  },
  {
    title: "Content engine",
    items: [
      { label: "Content gaps", path: "/content-gaps", soon: true },
      { label: "Content refreshes", path: "/content-refreshes", soon: true },
      { label: "Content calendar", path: "/content-calendar", soon: true },
    ],
  },
];

/** Settings holds the watchlist, so its page counts as being in Settings. */
const SETTINGS_PATHS = ["/settings", "/watchlist"];

const row = "block rounded-md px-3 py-1.5 text-sm font-semibold";

function useActive() {
  const { clientSlug } = useParams<{ clientSlug?: string }>();
  const pathname = usePathname();
  return { clientSlug, isActive: (path: string) => pathname.startsWith(`/${clientSlug}${path}`) };
}

/** The pages for the selected client, in groups. */
export function ClientNav() {
  const { clientSlug, isActive } = useActive();
  if (!clientSlug) return null;
  return (
    <div className="space-y-5">
      {GROUPS.map((group) => (
        <div key={group.title}>
          <h2 className="px-3 pb-1 text-[0.65rem] font-bold uppercase tracking-wider text-[var(--text-tertiary)]">{group.title}</h2>
          <ul className="space-y-0.5">
            {group.items.map((item) => (
              <li key={item.label}>
                {item.soon ? (
                  <span className="flex items-center justify-between rounded-md px-3 py-1.5 text-sm text-[var(--text-tertiary)]" title="Not built yet">
                    <span>{item.label}</span>
                    <span className="text-[0.6rem] uppercase tracking-wide">Soon</span>
                  </span>
                ) : (
                  <Link
                    href={`/${clientSlug}${item.path}`}
                    aria-current={isActive(item.path) ? "page" : undefined}
                    className={`${row} ${isActive(item.path) ? "bg-[var(--brand-teal)] text-white" : "text-[var(--text-primary)] hover:bg-[var(--border)]"}`}
                  >
                    {item.label}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Settings and, for admins, Admin: at the bottom of the sidebar, as in v1. */
export function SidebarFooter({ isAdmin }: { isAdmin: boolean }) {
  const { clientSlug, isActive } = useActive();
  const pathname = usePathname();
  const inSettings = clientSlug ? SETTINGS_PATHS.some((p) => isActive(p)) : false;
  const inAdmin = pathname.startsWith("/admin");
  return (
    <ul className="mt-auto space-y-0.5 border-t border-[var(--border)] pt-3">
      {clientSlug ? (
        <li>
          <Link href={`/${clientSlug}/settings`} aria-current={inSettings ? "page" : undefined} className={`${row} ${inSettings ? "bg-[var(--brand-teal)] text-white" : "text-[var(--text-primary)] hover:bg-[var(--border)]"}`}>
            Settings
          </Link>
        </li>
      ) : null}
      {isAdmin ? (
        <li>
          <Link href="/admin" aria-current={inAdmin ? "page" : undefined} className={`${row} ${inAdmin ? "bg-[var(--brand-teal)] text-white" : "text-[var(--text-primary)] hover:bg-[var(--border)]"}`}>
            Admin
          </Link>
        </li>
      ) : null}
    </ul>
  );
}
