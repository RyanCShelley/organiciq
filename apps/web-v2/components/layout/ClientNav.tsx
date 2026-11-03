"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

const PAGES = [
  { label: "Monthly review", path: "/review" },
  { label: "Business Intelligence", path: "/bi" },
  { label: "Decision engine", path: "/engine" },
  { label: "Search visibility", path: "/search-visibility" },
  { label: "LLM visibility", path: "/llm" },
  { label: "Watchlist", path: "/watchlist" },
  { label: "Settings", path: "/settings" },
] as const;

/** The pages that exist for the selected client. */
export function ClientNav() {
  const { clientSlug } = useParams<{ clientSlug?: string }>();
  const pathname = usePathname();
  if (!clientSlug) return null;

  return (
    <ul className="mb-4 space-y-1 border-b border-[var(--border)] pb-4">
      {PAGES.map((page) => {
        const href = `/${clientSlug}${page.path}`;
        const active = page.path ? pathname.startsWith(href) : pathname === href;
        return (
          <li key={page.label}>
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={`block rounded-md px-3 py-2 text-sm font-semibold ${
                active
                  ? "bg-[var(--brand-teal)] text-white"
                  : "text-[var(--text-primary)] hover:bg-[var(--border)]"
              }`}
            >
              {page.label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
