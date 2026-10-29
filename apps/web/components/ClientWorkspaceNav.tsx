"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { clientHref } from "@/lib/client-path";

const GROUPS = [
  { title: "Account", links: [["", "General Information"]] },
  { title: "Growth Engine Setup", links: [["integrations", "Connections"], ["conversions", "Conversions & Goals"], ["keyword-map", "Pages & Keywords"], ["competitors", "Competitors"]] },
  { title: "Administration", links: [["advanced", "Advanced Settings"], ["team", "Team Access"]] },
];
export function ClientWorkspaceNav({ clientSlug }: { clientSlug: string; active?: string }) {
  const path = usePathname();
  return <nav aria-label="Client settings" className="flex flex-wrap gap-1 lg:block lg:space-y-5">
    {GROUPS.map(group => <div key={group.title} className="contents lg:block">
      <p className="hidden lg:block px-3 pb-2 text-[10px] font-bold uppercase tracking-widest text-[var(--text-tertiary)]">{group.title}</p>
      <div className="contents lg:block">{group.links.map(([segment, label]) => {
        const href = clientHref(clientSlug, segment); const active = path === href;
        return <Link key={href} href={href} aria-current={active ? "page" : undefined} className={`block rounded-lg px-3 py-3 text-sm ${active ? "bg-[var(--brand-teal)]/10 font-semibold text-[var(--brand-teal)]" : "text-[var(--text-secondary)] hover:bg-[var(--surface-muted)]"}`}>{label}</Link>;
      })}</div>
    </div>)}
  </nav>;
}
export function ClientSettingsShell({ clientSlug, children }: { clientSlug: string; children: React.ReactNode }) {
  const path = usePathname();
  if (path.endsWith("/setup") || path.endsWith("/jobs") || path.endsWith("/data-health")) return <>{children}</>;
  return <div className="grid gap-6 lg:grid-cols-[210px_minmax(0,1fr)]"><ClientWorkspaceNav clientSlug={clientSlug} /><div className="min-w-0">{children}</div></div>;
}
export function ClientWorkspaceHeader({ clientName, domain }: { clientName: string; domain: string }) {
  return <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
    <div><p className="font-semibold">{clientName}</p><p className="mt-1 text-sm text-[var(--text-secondary)]">{domain}</p></div>
    <Link href="/clients" className="btn btn-secondary">All clients</Link>
  </div>;
}
