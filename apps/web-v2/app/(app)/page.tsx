import Link from "next/link";
import { unstable_rethrow } from "next/navigation";

import { AllClientsOverview } from "@/components/AllClientsOverview";
import { ApiError } from "@/lib/api";
import { getClientsOverview, type ClientsOverviewResponse } from "@/lib/overview";

export const metadata = { title: "All clients" };

export default async function HomePage() {
  let data: ClientsOverviewResponse | null = null;
  let error: string | null = null;

  try {
    data = await getClientsOverview();
  } catch (e) {
    unstable_rethrow(e);
    error =
      e instanceof ApiError && e.status === 403
        ? "Only SMA staff can view the all-clients overview."
        : e instanceof ApiError
          ? e.message
          : "The client overview could not be loaded: the API did not answer.";
  }

  if (error) {
    return (
      <section className="max-w-3xl space-y-4">
        <h1 className="font-[family-name:var(--font-display)] text-2xl font-bold">All clients</h1>
        <p role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
          {error}
        </p>
      </section>
    );
  }

  if (!data || data.clients.length === 0) {
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

  return <AllClientsOverview data={data} />;
}
