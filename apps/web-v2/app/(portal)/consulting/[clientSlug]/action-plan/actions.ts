"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { ClientRec } from "@/lib/portal";

export async function updateProgressAction(clientId: string, slug: string, id: string, body: Record<string, unknown>): Promise<{ ok: true; value: ClientRec } | { ok: false; error: string }> {
  try {
    const value = await apiFetch<ClientRec>(`/v2/consulting/portal/recommendations/${id}/progress`, { method: "POST", clientId, body });
    revalidatePath(`/consulting/${slug}`, "layout");
    return { ok: true, value };
  } catch (e) {
    return { ok: false, error: e instanceof ApiError ? e.message : "Could not save: the API did not answer." };
  }
}
