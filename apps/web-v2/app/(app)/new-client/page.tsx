import Link from "next/link";

import { NewClientForm } from "@/components/ClientForms";
import { getTiers } from "@/lib/clients";

export const metadata = { title: "Add client" };

export default async function NewClientPage() {
  const tiers = await getTiers();
  return (
    <section className="max-w-3xl space-y-6">
      <header>
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">Add a client</h1>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">The essentials. Everything else is on Settings. A company with several sites? <Link href="/new-client/sites" className="font-semibold text-[var(--brand-teal)] hover:underline">Add them together</Link>.</p>
      </header>
      <NewClientForm tiers={tiers} />
    </section>
  );
}
