"use client";

import { ChevronDown, ChevronRight, LogOut, Settings, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { LogoWordmark } from "@/components/brand/Logo";
import { ClientPicker } from "@/components/layout/ClientPicker";
import { GROUPS, SETTINGS_PATHS } from "@/components/layout/nav-config";
import type { Client } from "@/lib/api";

const SHUT_KEY = "oiq-nav-shut";

const link = "flex items-center gap-2 rounded-full px-3 py-1.5 text-sm";
const idle = "text-[var(--brand-teal-soft)] hover:bg-[var(--brand-navy-hover)] hover:text-white";
const active = "bg-[rgba(200,242,236,0.16)] font-semibold text-white";

/** The deep navy sidebar: logo, client picker, collapsible groups, then client settings, admin and the account. */
export function Sidebar({ clients, userEmail, isAdmin, signOutAction }: { clients: Client[]; userEmail?: string | null; isAdmin: boolean; signOutAction: () => Promise<void> }) {
  const { clientSlug } = useParams<{ clientSlug?: string }>();
  const pathname = usePathname();
  const isActive = (path: string) => pathname.startsWith(`/${clientSlug}${path}`);
  const current = clients.find((c) => c.slug === clientSlug);
  const onAds = !!current?.service_reporting?.ad_accelerator;
  const consulting = current?.service_mode === "consulting";
  const [shut, setShut] = useState<string[]>([]);

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(SHUT_KEY) ?? "[]");
      if (Array.isArray(saved)) setShut(saved.filter((x): x is string => typeof x === "string"));
    } catch {
      /* a group simply starts open */
    }
  }, []);
  const toggle = (title: string) =>
    setShut((cur) => {
      const next = cur.includes(title) ? cur.filter((t) => t !== title) : [...cur, title];
      try {
        localStorage.setItem(SHUT_KEY, JSON.stringify(next));
      } catch {
        /* kept for this visit only */
      }
      return next;
    });

  const inSettings = !!clientSlug && SETTINGS_PATHS.some((p) => isActive(p));
  const inAdmin = pathname.startsWith("/admin");

  return (
    <nav aria-label="Sections" className="sticky top-0 flex h-screen w-60 shrink-0 flex-col bg-[var(--brand-navy)] text-[var(--brand-teal-soft)]">
      <div className="px-4 pt-4">
        <Link href="/" aria-label="Organic IQ home">
          <LogoWordmark inverse className="text-[1.1rem]" />
        </Link>
      </div>
      <ClientPicker clients={clients} />

      <div className="mt-3 flex-1 space-y-1 overflow-y-auto px-2 pb-3">
        {clientSlug
          ? GROUPS.map((group) => {
              const isShut = shut.includes(group.title);
              const Icon = group.icon;
              return (
                <div key={group.title}>
                  <button
                    type="button"
                    aria-expanded={!isShut}
                    onClick={() => toggle(group.title)}
                    className="flex w-full items-center gap-2 rounded-full px-3 py-1.5 text-sm font-medium text-white hover:bg-[var(--brand-navy-hover)]"
                  >
                    <Icon size={16} className="text-[var(--brand-teal-soft)]" aria-hidden />
                    {group.title}
                    <ChevronDown size={14} className={`ml-auto text-[#8ea2ad] transition-transform ${isShut ? "-rotate-90" : ""}`} aria-hidden />
                  </button>
                  {isShut ? null : (
                    <ul className="mt-0.5 space-y-0.5">
                      {group.items.filter((item) => (!item.ads || onAds) && !(consulting && item.execution)).map((item) => (
                        <li key={item.label}>
                          <Link href={`/${clientSlug}${item.path}`} aria-current={isActive(item.path) ? "page" : undefined} className={`${link} pl-8 ${isActive(item.path) ? active : idle}`}>
                            {item.label}
                            {isActive(item.path) ? <ChevronRight size={14} className="ml-auto text-[var(--brand-teal-soft)]" aria-hidden /> : null}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              );
            })
          : null}
      </div>

      <div className="space-y-0.5 border-t border-[var(--brand-navy-line)] p-2">
        {clientSlug ? (
          <Link href={`/${clientSlug}/settings`} aria-current={inSettings ? "page" : undefined} className={`${link} ${inSettings ? active : idle}`}>
            <Settings size={16} aria-hidden /> Client settings
          </Link>
        ) : null}
        {isAdmin ? (
          <Link href="/admin" aria-current={inAdmin ? "page" : undefined} className={`${link} ${inAdmin ? active : idle}`}>
            <ShieldCheck size={16} aria-hidden /> Admin
          </Link>
        ) : null}
        <div className="flex items-center gap-2 px-2 pt-2">
          <span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[var(--brand-lime-soft)] text-[0.65rem] font-semibold text-[var(--brand-dark)]" aria-hidden>
            {(userEmail ?? "?")[0]?.toUpperCase()}
          </span>
          <span className="min-w-0 flex-1 truncate text-xs text-[#9db3bd]" title={userEmail ?? undefined}>{userEmail}</span>
          <form action={signOutAction}>
            <button type="submit" aria-label="Sign out" title="Sign out" className="rounded-md p-1.5 text-[#9db3bd] hover:bg-[var(--brand-navy-hover)] hover:text-white">
              <LogOut size={14} aria-hidden />
            </button>
          </form>
        </div>
      </div>
    </nav>
  );
}
