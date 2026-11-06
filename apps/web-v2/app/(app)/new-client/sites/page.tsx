import { AddSitesForm } from "@/components/AddSitesForm";
import { getTiers } from "@/lib/clients";

export const metadata = { title: "Add several sites" };

export default async function AddSitesPage() {
  const tiers = await getTiers();
  return (
    <section className="max-w-3xl space-y-6">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">Add several sites</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">For a company with more than one site. Each becomes its own client, grouped together.</p>
      </header>
      <AddSitesForm tiers={tiers} />
    </section>
  );
}
