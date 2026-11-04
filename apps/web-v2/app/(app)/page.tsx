import Link from "next/link";
import { redirect } from "next/navigation";

import { getClients } from "@/lib/clients";

export default async function HomePage() {
  const clients = await getClients().catch(() => []);
  const first = clients[0];
  if (first) redirect(`/${first.slug}`);

  return (
    <section>
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">No clients yet</h1>
      <p className="mt-2 text-sm text-[var(--text-secondary)]">
        You are signed in, but the API returned no clients for this account.
      </p>
      <Link
        href="/new-client"
        className="mt-4 inline-block rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white"
      >
        Add a client
      </Link>
    </section>
  );
}
