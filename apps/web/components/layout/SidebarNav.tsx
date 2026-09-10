"use client";

import { Bookmark, Eye, FileSearch, Gauge, LayoutDashboard, Settings, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { Logo } from "@/components/brand/Logo";
import { ClientSwitcher } from "@/components/layout/ClientSwitcher";
import { accountToolHref } from "@/lib/account-routes";
import type { Client } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  PLATFORM_NAV_ITEMS,
  accountNavGroups,
  isNavActive,
  isPlatformContext,
  withNavContext,
} from "@/lib/navigation";

const ACCOUNT_ICONS: Record<string, LucideIcon> = {
  Dashboard: LayoutDashboard,
  "Watch List": Eye,
  "Content Opp": FileSearch,
  "Decision Engine": Gauge,
  Annotations: Bookmark,
  "Client settings": Settings,
};

export function SidebarNav({
  clients,
  clientId,
  from,
  to,
  userEmail,
  signOutAction,
}: {
  clients: Client[];
  clientId: string;
  from: string;
  to: string;
  userEmail?: string | null;
  signOutAction: () => Promise<void>;
}) {
  const pathname = usePathname();
  const platformOnly = isPlatformContext(pathname);
  const accountToolMatch = pathname.match(
    /^\/([^/]+)\/(dashboard|watch-list|content-opp|decision-engine|annotations)(\/|$)/,
  );
  const clientsWorkspaceMatch = pathname.match(/^\/clients\/([^/]+)(?:\/|$)/);
  const pathSlug = accountToolMatch?.[1] || clientsWorkspaceMatch?.[1];
  const pathClient = pathSlug
    ? clients.find((client) => client.slug === pathSlug)
    : undefined;
  const effectiveClientId = pathClient?.id || clientId;
  const selected = clients.find((client) => client.id === effectiveClientId);
  const groups = accountNavGroups(selected?.slug ?? "");
  const logoHref = platformOnly
    ? withNavContext("/clients", effectiveClientId, from, to)
    : withNavContext(
        selected?.slug ? accountToolHref(selected.slug, "dashboard") : "/dashboard",
        effectiveClientId,
        from,
        to,
      );

  return (
    <aside className="sticky top-0 flex h-screen w-[var(--sidebar-width)] shrink-0 flex-col border-r border-[var(--border)] bg-[var(--surface)]">
      <div className="border-b border-[var(--border)] px-3 py-3">
        <Logo href={logoHref} />
      </div>

      {!platformOnly ? (
        <div className="border-b border-[var(--border)] px-3 py-3">
          <p className="mb-1.5 text-[0.625rem] font-semibold uppercase tracking-[0.07em] text-[var(--text-tertiary)]">
            Client
          </p>
          <Suspense fallback={<div className="h-10 rounded-lg bg-[var(--surface-muted)]" />}>
            <ClientSwitcher clients={clients} clientId={effectiveClientId} from={from} to={to} />
          </Suspense>
        </div>
      ) : null}

      <nav className="flex-1 overflow-y-auto px-2 py-3">
        {!platformOnly
          ? groups.map((group) => (
              <div key={group.label} className="mb-4 last:mb-0">
                <p className="mb-1 px-2 text-[0.625rem] font-semibold uppercase tracking-[0.07em] text-[var(--text-tertiary)]">
                  {group.label}
                </p>
                <ul className="space-y-0.5">
                  {group.items.map((item) => {
                    const active = isNavActive(pathname, item.href, item.exact);
                    const Icon = ACCOUNT_ICONS[item.label] ?? Settings;
                    return (
                      <li key={`${item.label}-${item.href}-${item.tab ?? ""}`}>
                        <Link
                          href={withNavContext(item.href, effectiveClientId, from, to, {
                            tab: item.tab,
                          })}
                          className={cn(
                            "relative flex items-center gap-2 rounded-md px-2 py-1.5 text-[0.8125rem] leading-tight transition-colors",
                            active
                              ? "sidebar-link-active"
                              : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]",
                          )}
                        >
                          <Icon className="h-3.5 w-3.5 shrink-0 opacity-75" aria-hidden />
                          <span>{item.label}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          : null}

        <div className={platformOnly ? undefined : "mt-2 border-t border-[var(--border)] pt-3"}>
          <p className="mb-1 px-2 text-[0.625rem] font-semibold uppercase tracking-[0.07em] text-[var(--text-tertiary)]">
            Platform
          </p>
          <ul className="space-y-0.5">
            {PLATFORM_NAV_ITEMS.map((item) => {
              const active = isNavActive(pathname, item.href, item.exact);
              return (
                <li key={item.href}>
                  <Link
                    href={withNavContext(item.href, clientId, from, to)}
                    className={cn(
                      "flex items-center rounded-md px-2 py-1.5 text-[0.8125rem] leading-tight transition-colors",
                      active
                        ? "sidebar-link-active relative"
                        : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]",
                    )}
                  >
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </nav>

      <div className="mt-auto border-t border-[var(--border)] px-3 py-3">
        {userEmail ? (
          <p className="truncate text-[0.75rem] text-[var(--text-secondary)]" title={userEmail}>
            {userEmail}
          </p>
        ) : null}
        <form action={signOutAction} className="mt-2">
          <button type="submit" className="btn btn-secondary btn-sm w-full">
            Sign out
          </button>
        </form>
      </div>
    </aside>
  );
}
