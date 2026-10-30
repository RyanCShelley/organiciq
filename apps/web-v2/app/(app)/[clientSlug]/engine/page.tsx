import { notFound } from "next/navigation";

import { EngineScreen } from "@/components/EngineScreen";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import { EMPTY_OVERVIEW, EMPTY_PLAN, type EngineOverview, type TaskPlan, type VisibilityCandidates } from "@/lib/engine";
import { currentMonth, type ClientFocus } from "@/lib/focus";
import { lastCompleteMonth } from "@/lib/review";
import type { Watchlist } from "@/lib/watchlist";

export const metadata = { title: "Decision engine" };

export default async function EnginePage({
  params,
  searchParams,
}: {
  params: Promise<{ clientSlug: string }>;
  searchParams: Promise<{ bucket?: string; show?: string }>;
}) {
  const { clientSlug } = await params;
  const { bucket: requestedBucket, show } = await searchParams;
  const client = (await getClients()).find((c) => c.slug === clientSlug);
  if (!client) notFound();

  const month = lastCompleteMonth();
  const workMonth = currentMonth();
  const [focus, watchlist, plan, team] = await Promise.all([
    apiFetch<ClientFocus | null>(`/v2/focus/${workMonth}`, { clientId: client.id }),
    apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id }),
    apiFetch<TaskPlan>(`/v2/engine/tasks?month=${workMonth}`, { clientId: client.id }).catch(() => EMPTY_PLAN),
    // Who can be assigned. Only an admin can list a client's team, so anyone else simply sees no picker.
    apiFetch<{ email: string; name: string | null; is_active: boolean }[]>(`/admin/clients/${client.id}/team`)
      .then((rows) => rows.filter((r) => r.is_active).map((r) => ({ email: r.email, name: r.name })))
      .catch(() => [] as { email: string; name: string | null }[]),
  ]);

  // The bucket in the URL wins; otherwise the one chosen with the focus; otherwise the whole site.
  const bucketId =
    requestedBucket === "site" ? null : (requestedBucket ?? focus?.bucket_id ?? null);
  const showVisibility = focus?.focus === "visibility" || show === "visibility";

  let data: VisibilityCandidates | null = null;
  let overview: EngineOverview = EMPTY_OVERVIEW;
  let error: string | null = null;
  if (showVisibility) {
    try {
      const focusBucket = focus?.bucket_id ? `&focus_bucket_id=${focus.bucket_id}` : "";
      overview = await apiFetch<EngineOverview>(`/v2/engine/visibility/buckets?month=${month}${focusBucket}`, {
        clientId: client.id,
      });
      const query = new URLSearchParams({ month });
      if (bucketId) query.set("bucket_id", bucketId);
      data = await apiFetch<VisibilityCandidates>(`/v2/engine/visibility?${query}`, { clientId: client.id });
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The candidate list could not be built: the API did not answer.";
    }
  }

  return (
    <EngineScreen
      client={client}
      workMonth={workMonth}
      focus={focus}
      buckets={watchlist.buckets.map((b) => ({ id: b.id, name: b.name }))}
      bucketId={bucketId}
      showVisibility={showVisibility}
      data={data}
      overview={overview}
      plan={plan}
      team={team}
      error={error}
    />
  );
}
