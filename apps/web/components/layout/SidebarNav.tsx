"use client";

import {
  Activity,
  Bookmark,
  Eye,
  FileSearch,
  Gauge,
  LayoutDashboard,
  LayoutGrid,
  RefreshCw,
  Settings2,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

import { LogoWordmark } from "@/components/brand/Logo";
import { ClientSwitcher } from "@/components/layout/ClientSwitcher";
import { accountToolHref } from "@/lib/account-routes";
import type { Client } from "@/lib/api";
import { BRAND } from "@/lib/brand";
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
  "Client settings": Settings2,
};

const PLATFORM_ICONS: Record<string, LucideIcon> = {
  "All clients": LayoutGrid,
  Overview: LayoutGrid,
  "Data health": Activity,
  "Sync jobs": RefreshCw,
  Settings: Settings2,
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
    <aside className="sticky top-0 flex h-screen w-[var(--sidebar-width)] shrink-0 flex-col border-r border-[var(--sidebar-border)] bg-[var(--sidebar-bg)]">
      <div className="border-b border-[var(--sidebar-border)] px-[18px] pb-3.5 pt-[18px]">
        <Link href={logoHref} className="inline-flex flex-col" aria-label={`${BRAND.logoWordmark} home`}>
          <LogoWordmark inverse className="text-[19px] font-black" />
          <span className="mt-1 text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--sidebar-fg-muted)]">
            {BRAND.companyName}
          </span>
        </Link>
      </div>

      {!platformOnly ? (
        <div className="border-b border-[var(--sidebar-border)] px-3.5 py-3.5">
          <p className="mb-1.5 px-0.5 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--sidebar-fg-muted)]">
            Client
          </p>
          <Suspense fallback={<div className="h-11 rounded-[10px] bg-[var(--sidebar-field)]" />}>
            <ClientSwitcher
              clients={clients}
              clientId={effectiveClientId}
              from={from}
              to={to}
              tone="dark"
            />
          </Suspense>
        </div>
      ) : null}

      <nav className="flex flex-1 flex-col gap-[18px] overflow-y-auto px-2.5 py-3.5">
        {!platformOnly
          ? groups.map((group) => (
              <div key={group.label}>
                <p className="mb-1.5 px-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--sidebar-fg-muted)]">
                  {group.label}
                </p>
                <ul className="space-y-0.5">
                  {group.items.map((item) => {
                    const active = isNavActive(pathname, item.href, item.exact);
                    const Icon = ACCOUNT_ICONS[item.label] ?? Settings2;
                    return (
                      <li key={`${item.label}-${item.href}-${item.tab ?? ""}`}>
                        <Link
                          href={withNavContext(item.href, effectiveClientId, from, to, {
                            tab: item.tab,
                          })}
                          className={cn(
                            "relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] leading-tight transition-colors duration-[120ms]",
                            active
                              ? "sidebar-link-active"
                              : "text-white hover:bg-[var(--sidebar-field)]",
                          )}
                        >
                          <Icon className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden />
                          <span>{item.label}</span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))
          : null}

        <div
          className={cn(
            !platformOnly && "mt-auto border-t border-[var(--sidebar-border)] pt-3.5",
          )}
        >
          <p className="mb-1.5 px-2 text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--sidebar-fg-muted)]">
            Platform
          </p>
          <ul className="space-y-0.5">
            {PLATFORM_NAV_ITEMS.map((item) => {
              const active = isNavActive(pathname, item.href, item.exact);
              const Icon = PLATFORM_ICONS[item.label] ?? LayoutGrid;
              return (
                <li key={item.href}>
                  <Link
                    href={withNavContext(item.href, clientId, from, to)}
                    className={cn(
                      "relative flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-[13.5px] leading-tight transition-colors duration-[120ms]",
                      active
                        ? "sidebar-link-active"
                        : "text-white hover:bg-[var(--sidebar-field)]",
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" strokeWidth={2} aria-hidden />
                    <span>{item.label}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      </nav>

      <div className="mt-auto border-t border-[var(--sidebar-border)] px-3.5 py-3.5">
        {userEmail ? (
          <p
            className="truncate text-xs text-[var(--sidebar-fg-muted)]"
            title={userEmail}
          >
            {userEmail}
          </p>
        ) : null}
        <form action={signOutAction} className="mt-2.5">
          <button
            type="submit"
            className="w-full rounded-lg border border-[var(--sidebar-border-strong)] bg-transparent px-2.5 py-2 text-[12.5px] font-semibold text-[var(--sidebar-fg)] transition-colors duration-[120ms] hover:bg-[var(--sidebar-field)]"
          >
            Sign out
          </button>
        </form>
      </div>
    </aside>
  );
}
