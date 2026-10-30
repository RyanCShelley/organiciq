import { notFound } from "next/navigation";

import { ReviewScreen } from "@/components/ReviewScreen";
import { DataFreshness } from "@/components/DataFreshness";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { ClientFocus } from "@/lib/focus";
import { EMPTY_OVERVIEW, type EngineOverview } from "@/lib/engine";
import { lastCompleteMonth, nextMonth, type Review } from "@/lib/review";
import type { Watchlist } from "@/lib/watchlist";

export const metadata = { title: "Monthly review" };

export default async function ReviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ month?: string }>;
}) {
  const { clientSlug } = await params;
  const { month: requested } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const month = requested && /^\d{4}-(0[1-9]|1[0-2])$/.test(requested) ? requested : lastCompleteMonth();
  const planMonth = nextMonth(month);

  let review: Review | null = null;
  let error: string | null = null;
  try {
    review = await apiFetch<Review>(`/v2/review?month=${month}`, { clientId: client.id });
  } catch (e) {
    error = e instanceof ApiError ? e.message : "The review could not be built: the API did not answer.";
  }

  const [focus, watchlist, reach] = await Promise.all([
    apiFetch<ClientFocus | null>(`/v2/focus/${planMonth}`, { clientId: client.id }),
    apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id }),
    // Reach is a hint beside the choice; the review still works without it.
    apiFetch<EngineOverview>(`/v2/engine/visibility/buckets?month=${month}`, { clientId: client.id }).catch(
      () => EMPTY_OVERVIEW,
    ),
  ]);

  return (
    <>
    <DataFreshness clientId={client.id} />
    <ReviewScreen
      client={client}
      month={month}
      planMonth={planMonth}
      review={review}
      error={error}
      focus={focus}
      buckets={watchlist.buckets.map((b) => ({ id: b.id, name: b.name }))}
      reach={reach.buckets}
    />
    </>
  );
}
