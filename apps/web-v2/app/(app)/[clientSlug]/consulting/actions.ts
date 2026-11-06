"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { Profile } from "@/lib/portal";

export async function saveProfileAction(clientId: string, slug: string, fields: Partial<Profile> | Record<string, unknown>): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    await apiFetch("/v2/consulting/profile", { method: "PUT", clientId, body: fields });
    revalidatePath(`/${slug}/consulting`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof ApiError ? e.message : "Could not save: the API did not answer." };
  }
}
