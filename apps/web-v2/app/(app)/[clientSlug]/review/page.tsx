import { notFound } from "next/navigation";

import { ReviewScreen } from "@/components/ReviewScreen";
import { Suspense } from "react";

import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import type { ClientFocus } from "@/lib/focus";
import type { ShippedResult } from "@/lib/engine";
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

  // Everything this page needs is asked at once; it waits for the slowest, not for each in turn.
  const reviewPromise = apiFetch<Review>(`/v2/review?month=${month}`, { clientId: client.id }).then(
    (r) => ({ review: r, error: null as string | null }),
    (e) => ({ review: null as Review | null, error: e instanceof ApiError ? e.message : "The review could not be built: the API did not answer." }),
  );
  const [{ review, error }, focus, watchlist, shipped] = await Promise.all([
    reviewPromise,
    apiFetch<ClientFocus | null>(`/v2/focus/${planMonth}`, { clientId: client.id }),
    apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id }),
    apiFetch<ShippedResult[]>("/v2/engine/tasks/results", { clientId: client.id }).catch(() => [] as ShippedResult[]),
  ]);

  return (
    <>
    <Suspense fallback={null}>
    </Suspense>
    <ReviewScreen
      client={client}
      month={month}
      planMonth={planMonth}
      review={review}
      error={error}
      focus={focus}
      buckets={watchlist.buckets.map((b) => ({ id: b.id, name: b.name }))}
      shipped={shipped}
    />
    </>
  );
}
