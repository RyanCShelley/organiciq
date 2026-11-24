"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";

import { resolveStepHref, type SetupState } from "@/components/SetupChecklist";

const TABS: readonly { label: string; path: string; href?: string }[] = [
  { label: "General", path: "" },
  { label: "Connections", path: "/connections" },
  { label: "Conversions & goals", path: "/conversions" },
  { label: "Content sources", path: "/content" },
  { label: "Watchlist", path: "", href: "/watchlist" },
  { label: "Competitors", path: "/competitors" },
  { label: "Baseline", path: "/baseline" },
  { label: "Advanced", path: "/advanced" },
  { label: "Team access", path: "/team" },
];

export function SettingsTabs({ setup }: { setup?: SetupState | null }) {
  const { clientSlug } = useParams<{ clientSlug: string }>();
  const pathname = usePathname();
  const nextStep = setup?.next ? setup.steps.find((s) => s.key === setup.next) ?? null : null;
  const nextHref = nextStep ? resolveStepHref(clientSlug, nextStep, setup?.service_mode ?? "execution") : null;

  return (
    <nav aria-label="Settings sections" className="flex flex-wrap gap-0.5 border-b border-[var(--border)]">
      {TABS.map((tab) => {
        const href = tab.href ? `/${clientSlug}${tab.href}` : `/${clientSlug}/settings${tab.path}`;
        const active = pathname === href;
        const isNextTab = nextHref === href;
        return (
          <Link
            key={tab.label}
            href={href}
            aria-current={active ? "page" : undefined}
            className={`-mb-px inline-flex items-center gap-1.5 border-b-2 px-2.5 py-2 text-[0.8125rem] font-semibold ${
              active
                ? "border-[var(--brand-teal)] text-[var(--brand-teal)]"
                : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            <span>{tab.label}</span>
            {isNextTab ? (
              <span
                className="h-1.5 w-1.5 rounded-full bg-[var(--brand-teal)]"
                title="Next setup step"
                aria-label="Next setup step"
              />
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}
