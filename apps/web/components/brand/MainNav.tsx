"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/watch-list", label: "Watch List" },
  { href: "/content-opp", label: "Content Opp" },
  { href: "/decision-engine", label: "Decision Engine" },
  { href: "/activity", label: "Activity" },
  { href: "/client-strategy", label: "Client Strategy" },
  { href: "/platform", label: "Platform" },
  { href: "/clients", label: "Clients" },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") return pathname === "/dashboard";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function MainNav({
  clientId,
  from,
  to,
}: {
  clientId: string;
  from: string;
  to: string;
}) {
  const pathname = usePathname();

  return (
    <nav className="flex flex-wrap gap-1 text-sm">
      {NAV.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={withContext(item.href, clientId, from, to)}
            className={`rounded-full px-3 py-1.5 transition ${
              active
                ? "nav-link-active"
                : "text-[var(--muted)] hover:bg-white/5 hover:text-[var(--foreground)]"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

function withContext(href: string, clientId: string, from: string, to: string): string {
  const params = new URLSearchParams();
  if (clientId) params.set("clientId", clientId);
  if (from) params.set("from", from);
  if (to) params.set("to", to);
  const qs = params.toString();
  return qs ? `${href}?${qs}` : href;
}
