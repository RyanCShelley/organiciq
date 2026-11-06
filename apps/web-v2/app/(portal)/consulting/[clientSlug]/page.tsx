import { getPortals } from "@/lib/portal";

export const metadata = { title: "Consulting portal" };

export default async function PortalDashboard({ params }: { params: Promise<{ clientSlug: string }> }) {
  const { clientSlug } = await params;
  const site = (await getPortals().catch(() => null))?.clients.find((c) => c.slug === clientSlug);
  return (
    <section className="space-y-4">
      <h1 className="text-2xl font-bold">Welcome{site ? `, ${site.name}` : ""}</h1>
      <p className="max-w-2xl text-sm text-[var(--text-secondary)]">
        This is where your consultant shares what changed in your search and AI visibility, traffic and leads, why it matters, and what your team can do next. Nothing has been published here yet.
      </p>
    </section>
  );
}
