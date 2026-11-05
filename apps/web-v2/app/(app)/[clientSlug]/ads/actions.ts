"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

/** Write down a change made to the Google Ads account. It shows under "Work completed" and splits the month into before and after. */
export async function addAdsNoteAction(clientId: string, slug: string, date: string, text: string): Promise<Result> {
  try {
    await apiFetch("/v2/ads/notes", { method: "POST", clientId, body: { date, text } });
    revalidatePath(`/${slug}/ads`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof ApiError ? e.message : "The note could not be saved: the API did not answer." };
  }
}

/** Take a note off the account's list of work done. */
export async function removeAdsNoteAction(clientId: string, slug: string, id: string): Promise<Result> {
  try {
    await apiFetch(`/v2/ads/notes/${id}`, { method: "DELETE", clientId });
    revalidatePath(`/${slug}/ads`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof ApiError ? e.message : "The note could not be removed: the API did not answer." };
  }
}
