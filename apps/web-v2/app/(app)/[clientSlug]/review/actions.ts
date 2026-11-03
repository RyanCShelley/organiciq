"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { BucketOverview, EngineOverview } from "@/lib/engine";

/** Throw away the kept review of a month and work it out again from the data held now. */
export async function rerunReviewAction(clientId: string, slug: string, month: string): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await apiFetch(`/v2/review/rerun?month=${encodeURIComponent(month)}`, { method: "POST", clientId });
    revalidatePath(`/${slug}/review`);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The review could not be worked out again: the API did not answer." };
  }
}

/** Each bucket's reach for the focus choice. A hint: if it cannot be read, the choice simply shows without it. */
export async function reachAction(clientId: string, month: string): Promise<BucketOverview[]> {
  try {
    const overview = await apiFetch<EngineOverview>(`/v2/engine/visibility/buckets?month=${encodeURIComponent(month)}`, { clientId });
    return overview.buckets;
  } catch {
    return [];
  }
}
