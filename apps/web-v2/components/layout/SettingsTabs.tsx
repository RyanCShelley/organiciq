"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

const TABS = [
  { label: "General", path: "" },
  { label: "Connections", path: "/connections" },
  { label: "Content sources", path: "/content" },
  { label: "Watchlist import", path: "/watchlist" },
  { label: "Competitors", path: "/competitors" },
  { label: "Advanced", path: "/advanced" },
  { label: "Team access", path: "/team" },
] as const;

export function SettingsTabs() {
  const { clientSlug } = useParams<{ clientSlug: string }>();
  const pathname = usePathname();
  return (
    <nav aria-label="Settings sections" className="flex flex-wrap gap-1 border-b border-[var(--border)]">
      {TABS.map((tab) => {
        const href = `/${clientSlug}/settings${tab.path}`;
        const active = pathname === href;
        return (
          <Link
            key={tab.label}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold ${
              active
                ? "border-[var(--brand-teal)] text-[var(--brand-teal)]"
                : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {tab.label}
          </Link>
        );
      })}
    </nav>
  );
}
