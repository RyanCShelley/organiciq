"use server";

import { revalidatePath } from "next/cache";
import { unstable_rethrow } from "next/navigation";

import { ApiError, apiFetch } from "@/lib/api";
import type { SvDetail } from "@/lib/search-visibility";

function revalidateWatchlistSearchRoutes(slug?: string) {
  if (!slug) return;
  revalidatePath(`/${slug}/search-visibility`);
  revalidatePath(`/${slug}/watchlist`);
  revalidatePath(`/${slug}/settings/watchlist`);
  revalidatePath(`/${slug}/focus`);
}

export async function termDetailAction(clientId: string, term: string, from: string, to: string): Promise<{ ok: true; detail: SvDetail } | { ok: false; error: string }> {
  try {
    const q = new URLSearchParams({ term, from, to });
    return { ok: true, detail: await apiFetch<SvDetail>(`/v2/search-visibility/term?${q}`, { clientId }) };
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The term could not be read: the API did not answer." };
  }
}

export async function addWatchlistKeywordAction(
  clientId: string,
  payload: { keyword: string; bucket_id?: string | null; bucket_name?: string | null; notes?: string | null },
  slug?: string,
): Promise<
  | {
      ok: true;
      result: {
        id: string;
        keyword: string;
        keyword_key: string;
        bucket_id: string;
        bucket_name: string;
        created: boolean;
        bucket_created: boolean;
      };
    }
  | { ok: false; error: string }
> {
  try {
    const result = await apiFetch<{
      id: string;
      keyword: string;
      keyword_key: string;
      bucket_id: string;
      bucket_name: string;
      created: boolean;
      bucket_created: boolean;
    }>("/v2/watchlist/keywords", { method: "POST", clientId, body: payload });
    revalidateWatchlistSearchRoutes(slug);
    return { ok: true, result };
  } catch (error) {
    unstable_rethrow(error);
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "The keyword could not be added: the API did not answer.",
    };
  }
}

export async function removeWatchlistKeywordAction(
  clientId: string,
  keywordId: string,
  slug?: string,
): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await apiFetch<void>(`/v2/watchlist/keywords/${encodeURIComponent(keywordId)}`, {
      method: "DELETE",
      clientId,
    });
    revalidateWatchlistSearchRoutes(slug);
    return { ok: true };
  } catch (error) {
    unstable_rethrow(error);
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "The keyword could not be removed: the API did not answer.",
    };
  }
}

export async function logVisibilityCheckAction(
  clientId: string,
  date: string,
  description: string,
  page?: string,
  notes?: string,
): Promise<{ ok: true; id: string } | { ok: false; error: string }> {
  try {
    const res = await apiFetch<{ id: string }>("/v2/annotations", {
      method: "POST",
      clientId,
      body: {
        date,
        description,
        notes: notes?.trim() || null,
        page: page?.trim() || null,
        type: "visibility_check",
      },
    });
    return { ok: true, id: res.id };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "The visibility check could not be saved: the API did not answer.",
    };
  }
}
