"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/** The portal's own menu. Pages are added here as they are built; a client sees only what is published on them. */
const ITEMS = [{ label: "Dashboard", path: "" }];

export function PortalNav({ slug }: { slug: string }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Portal" className="flex gap-1">
      {ITEMS.map((item) => {
        const href = `/consulting/${slug}${item.path}`;
        const on = item.path === "" ? pathname === href : pathname.startsWith(href);
        return (
          <Link key={item.label} href={href} aria-current={on ? "page" : undefined} className={`-mb-px border-b-2 px-3 py-2 text-sm font-semibold ${on ? "border-[var(--brand-teal)] text-[var(--brand-teal)]" : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
