import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { PortalNav } from "@/components/portal/PortalNav";
import { ApiError, apiFetch } from "@/lib/api";
import { auth } from "@/lib/auth";
import { getPortals, type PortalHome } from "@/lib/portal";

export default async function PortalLayout({ children, params }: { children: React.ReactNode; params: Promise<{ clientSlug: string }> }) {
  const session = await auth();
  if (!session) redirect("/login");
  const { clientSlug } = await params;
  const portals = await getPortals().catch(() => null);
  const site = portals?.clients.find((c) => c.slug === clientSlug);
  if (!site) notFound();
  let home: PortalHome | null = null;
  try {
    home = await apiFetch<PortalHome>("/v2/consulting/portal", { clientId: site.id });
  } catch (e) {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404)) notFound();
  }
  const others = portals?.clients.filter((c) => c.id !== site.id) ?? [];
  return (
    <div className="min-h-screen bg-[var(--background)]">
      {home?.previewing ? (
        <div className="flex flex-wrap items-center justify-between gap-2 bg-amber-50 px-6 py-2 text-xs text-amber-900">
          <span><span className="font-semibold">Client view.</span> This is what {site.name} sees. Only published material appears here.</span>
          <Link href={`/${site.slug}/consulting`} className="font-semibold underline">Back to the consultant workspace</Link>
        </div>
      ) : null}
      <header className="border-b border-[var(--border)] bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6 py-4">
          <div>
            <div className="text-lg font-bold">{site.name}</div>
            <div className="text-xs text-[var(--text-secondary)]">{site.domain}</div>
          </div>
          <div className="text-right text-xs text-[var(--text-secondary)]">
            <div className="font-semibold text-[var(--text-primary)]">{home?.brand.name ?? "SMA Marketing"}</div>
            <div>Search and AI visibility consulting · powered by {home?.brand.powered_by ?? "Organic IQ"}</div>
          </div>
        </div>
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-6">
          <PortalNav slug={site.slug} />
          {others.length ? (
            <details className="relative pb-2 text-sm">
              <summary className="cursor-pointer font-semibold text-[var(--brand-teal)]">Other sites</summary>
              <ul className="absolute right-0 z-10 mt-1 min-w-48 rounded-lg border border-[var(--border)] bg-white p-1 shadow-lg">
                {others.map((o) => (
                  <li key={o.id}><Link href={`/consulting/${o.slug}`} className="block rounded px-2 py-1.5 hover:bg-[var(--background)]">{o.name}<span className="block text-xs text-[var(--text-secondary)]">{o.domain}</span></Link></li>
                ))}
              </ul>
            </details>
          ) : null}
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
    </div>
  );
}
