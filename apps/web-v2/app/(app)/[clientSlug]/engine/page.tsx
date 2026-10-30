import { notFound } from "next/navigation";

import { EngineScreen } from "@/components/EngineScreen";
import { DataFreshness } from "@/components/DataFreshness";
import { ApiError, apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";
import {
  EMPTY_OVERVIEW,
  EMPTY_PLAN,
  type EngineKind,
  type EngineOverview,
  type LeadsCandidates,
  type TaskPlan,
  type TopicGroup,
  type TrafficCandidates,
  type VisibilityCandidates,
} from "@/lib/engine";
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
  const [focus, watchlist, plan, team, topics] = await Promise.all([
    apiFetch<ClientFocus | null>(`/v2/focus/${workMonth}`, { clientId: client.id }),
    apiFetch<Watchlist>("/v2/watchlist", { clientId: client.id }),
    apiFetch<TaskPlan>(`/v2/engine/tasks?month=${workMonth}`, { clientId: client.id }).catch(() => EMPTY_PLAN),
    // Who can be assigned. Only an admin can list a client's team, so anyone else simply sees no picker.
    apiFetch<{ email: string; name: string | null; is_active: boolean }[]>(`/admin/clients/${client.id}/team`)
      .then((rows) => rows.filter((r) => r.is_active).map((r) => ({ email: r.email, name: r.name })))
      .catch(() => [] as { email: string; name: string | null }[]),
    apiFetch<TopicGroup[]>("/v2/engine/topics", { clientId: client.id }).catch(() => [] as TopicGroup[]),
  ]);

  // The bucket in the URL wins; otherwise the one chosen with the focus; otherwise the whole site.
  const bucketId =
    requestedBucket === "site" ? null : (requestedBucket ?? focus?.bucket_id ?? null);
  // A tab in the URL wins; otherwise the focus chosen for this month.
  const kind: EngineKind | null =
    show === "visibility" || show === "traffic" || show === "leads" ? show : (focus?.focus ?? null);

  let data: VisibilityCandidates | null = null;
  let traffic: TrafficCandidates | null = null;
  let leads: LeadsCandidates | null = null;
  let overview: EngineOverview = EMPTY_OVERVIEW;
  let error: string | null = null;
  if (kind === "traffic" || kind === "leads") {
    try {
      const query = new URLSearchParams({ month });
      if (bucketId) query.set("bucket_id", bucketId);
      if (kind === "traffic") traffic = await apiFetch<TrafficCandidates>(`/v2/engine/traffic?${query}`, { clientId: client.id });
      else leads = await apiFetch<LeadsCandidates>(`/v2/engine/leads?${query}`, { clientId: client.id });
    } catch (e) {
      error = e instanceof ApiError ? e.message : "The candidate list could not be built: the API did not answer.";
    }
  }
  if (kind === "visibility") {
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
    <>
    <DataFreshness clientId={client.id} />
    <EngineScreen
      topics={topics}
      client={client}
      workMonth={workMonth}
      focus={focus}
      buckets={watchlist.buckets.map((b) => ({ id: b.id, name: b.name }))}
      bucketId={bucketId}
      kind={kind}
      data={data}
      traffic={traffic}
      leads={leads}
      overview={overview}
      plan={plan}
      team={team}
      error={error}
    />
    </>
  );
}
