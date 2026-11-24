"use server";

import { revalidatePath } from "next/cache";
import { unstable_rethrow } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import type {
  ActionResult,
  ImportReport,
  ImportResult,
  WatchlistBucket,
  WatchlistBucketDeleteResponse,
  WatchlistKeywordAddResponse,
  WatchlistKeywordBulkAddResponse,
  WatchlistKeywordCreateInput,
  WatchlistKeywordDetail,
  WatchlistKeywordUpdateInput,
  WatchlistSuggestionsResponse,
} from "@/lib/watchlist";

function revalidateWatchlistRoutes(slug: string) {
  if (!slug) return;
  revalidatePath(`/${slug}/watchlist`);
  revalidatePath(`/${slug}/settings/watchlist`);
  revalidatePath(`/${slug}/settings`);
  revalidatePath(`/${slug}/settings/baseline`);
  revalidatePath(`/${slug}/content-gaps`);
  revalidatePath(`/${slug}/search-visibility`);
  revalidatePath(`/${slug}/focus`);
  revalidatePath(`/${slug}/review`);
  revalidatePath(`/${slug}/engine`);
}

function actionError(error: unknown, fallback: string): { ok: false; error: string; status?: number } {
  unstable_rethrow(error);
  if (error instanceof ApiError) {
    const message =
      error.status === 422 && error.message === "Request failed"
        ? "Check the highlighted input values and try again."
        : error.message;
    return { ok: false, error: message, status: error.status };
  }
  return { ok: false, error: fallback };
}

export async function importWatchlistAction(
  clientId: string,
  slug: string,
  csvText: string,
  dryRun: boolean,
): Promise<ImportResult> {
  if (!clientId || !csvText.trim()) return { ok: false, error: "Choose a CSV file first." };
  try {
    const report = await apiFetch<ImportReport>("/v2/watchlist/import", {
      method: "POST",
      clientId,
      body: { csv_text: csvText, dry_run: dryRun },
    });
    if (!dryRun) revalidateWatchlistRoutes(slug);
    return { ok: true, report };
  } catch (error) {
    unstable_rethrow(error);
    if (error instanceof ApiError) return { ok: false, error: error.message };
    return { ok: false, error: "The import could not reach the API." };
  }
}

export async function addKeywordAction(
  clientId: string,
  slug: string,
  payload: WatchlistKeywordCreateInput,
): Promise<ActionResult<WatchlistKeywordAddResponse>> {
  try {
    const data = await apiFetch<WatchlistKeywordAddResponse>("/v2/watchlist/keywords", {
      method: "POST",
      clientId,
      body: payload,
    });
    revalidateWatchlistRoutes(slug);
    return { ok: true, data };
  } catch (error) {
    return actionError(error, "The keyword could not be added.");
  }
}

export async function updateKeywordAction(
  clientId: string,
  slug: string,
  keywordId: string,
  payload: WatchlistKeywordUpdateInput,
): Promise<ActionResult<WatchlistKeywordDetail>> {
  try {
    const data = await apiFetch<WatchlistKeywordDetail>(
      `/v2/watchlist/keywords/${encodeURIComponent(keywordId)}`,
      {
        method: "PATCH",
        clientId,
        body: payload,
      },
    );
    revalidateWatchlistRoutes(slug);
    return { ok: true, data };
  } catch (error) {
    return actionError(error, "The keyword could not be updated.");
  }
}

export async function deleteKeywordAction(
  clientId: string,
  slug: string,
  keywordId: string,
): Promise<ActionResult<null>> {
  try {
    await apiFetch<void>(`/v2/watchlist/keywords/${encodeURIComponent(keywordId)}`, {
      method: "DELETE",
      clientId,
    });
    revalidateWatchlistRoutes(slug);
    return { ok: true, data: null };
  } catch (error) {
    return actionError(error, "The keyword could not be deleted.");
  }
}

export async function createBucketAction(
  clientId: string,
  slug: string,
  payload: { name: string; sort_order?: number },
): Promise<ActionResult<WatchlistBucket>> {
  try {
    const data = await apiFetch<WatchlistBucket>("/v2/watchlist/buckets", {
      method: "POST",
      clientId,
      body: { name: payload.name.trim(), ...(payload.sort_order !== undefined ? { sort_order: payload.sort_order } : {}) },
    });
    revalidateWatchlistRoutes(slug);
    return { ok: true, data };
  } catch (error) {
    return actionError(error, "The bucket could not be created.");
  }
}

export async function updateBucketAction(
  clientId: string,
  slug: string,
  bucketId: string,
  payload: { name?: string; sort_order?: number },
): Promise<ActionResult<WatchlistBucket>> {
  try {
    const body: { name?: string; sort_order?: number } = {};
    if (payload.name !== undefined) body.name = payload.name.trim();
    if (payload.sort_order !== undefined) body.sort_order = payload.sort_order;
    const data = await apiFetch<WatchlistBucket>(
      `/v2/watchlist/buckets/${encodeURIComponent(bucketId)}`,
      {
        method: "PATCH",
        clientId,
        body,
      },
    );
    revalidateWatchlistRoutes(slug);
    return { ok: true, data };
  } catch (error) {
    return actionError(error, "The bucket could not be updated.");
  }
}

export async function deleteBucketAction(
  clientId: string,
  slug: string,
  bucketId: string,
  confirm = false,
): Promise<ActionResult<WatchlistBucketDeleteResponse>> {
  try {
    const qs = confirm ? "?confirm=true" : "";
    const data = await apiFetch<WatchlistBucketDeleteResponse>(
      `/v2/watchlist/buckets/${encodeURIComponent(bucketId)}${qs}`,
      {
        method: "DELETE",
        clientId,
      },
    );
    revalidateWatchlistRoutes(slug);
    return { ok: true, data };
  } catch (error) {
    return actionError(error, "The bucket could not be deleted.");
  }
}

export async function fetchWatchlistSuggestionsAction(
  clientId: string,
  params?: { search?: string; days?: number; limit?: number },
): Promise<ActionResult<WatchlistSuggestionsResponse>> {
  try {
    const qs = new URLSearchParams();
    if (params?.days !== undefined) qs.set("days", String(params.days));
    if (params?.limit !== undefined) qs.set("limit", String(params.limit));
    if (params?.search?.trim()) qs.set("search", params.search.trim());
    const query = qs.toString();
    const data = await apiFetch<WatchlistSuggestionsResponse>(
      `/v2/watchlist/suggestions${query ? `?${query}` : ""}`,
      { clientId },
    );
    return { ok: true, data };
  } catch (error) {
    return actionError(error, "Search Console suggestions could not be loaded.");
  }
}

export async function bulkAddKeywordsAction(
  clientId: string,
  slug: string,
  items: WatchlistKeywordCreateInput[],
): Promise<ActionResult<WatchlistKeywordBulkAddResponse>> {
  if (items.length === 0) {
    return { ok: false, error: "Select at least one keyword to add." };
  }
  try {
    const data = await apiFetch<WatchlistKeywordBulkAddResponse>("/v2/watchlist/keywords/bulk", {
      method: "POST",
      clientId,
      body: { items },
    });
    revalidateWatchlistRoutes(slug);
    return { ok: true, data };
  } catch (error) {
    return actionError(error, "The selected keywords could not be added.");
  }
}
