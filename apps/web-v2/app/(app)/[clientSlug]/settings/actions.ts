"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { FeedActionResult } from "@/lib/feeds";

function failure(error: unknown, fallback: string): FeedActionResult {
  return { ok: false, error: error instanceof ApiError ? error.message : fallback };
}

export async function addFeedAction(
  clientId: string,
  slug: string,
  url: string,
  label: string,
): Promise<FeedActionResult> {
  if (!url.trim()) return { ok: false, error: "Enter the feed address." };
  try {
    await apiFetch("/v2/feeds", { method: "POST", clientId, body: { url, label } });
    revalidatePath(`/${slug}/settings`);
    return { ok: true };
  } catch (error) {
    return failure(error, "The feed could not be saved: the API did not answer.");
  }
}

export async function removeFeedAction(
  clientId: string,
  slug: string,
  feedId: string,
): Promise<FeedActionResult> {
  try {
    await apiFetch(`/v2/feeds/${feedId}`, { method: "DELETE", clientId });
    revalidatePath(`/${slug}/settings`);
    return { ok: true };
  } catch (error) {
    return failure(error, "The feed could not be removed: the API did not answer.");
  }
}
