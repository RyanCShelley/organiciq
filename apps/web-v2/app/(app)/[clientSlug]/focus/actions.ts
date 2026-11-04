"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { FocusActionResult } from "@/lib/focus";

function failure(error: unknown, fallback: string): FocusActionResult {
  return { ok: false, error: error instanceof ApiError ? error.message : fallback };
}

export async function saveFocusAction(
  clientId: string,
  slug: string,
  month: string,
  focus: string,
  bucketId: string | null,
): Promise<FocusActionResult> {
  try {
    await apiFetch(`/v2/focus/${month}`, {
      method: "PUT",
      clientId,
      body: { focus, bucket_id: bucketId },
    });
    revalidatePath(`/${slug}/focus`);
    return { ok: true };
  } catch (error) {
    return failure(error, "The focus could not be saved: the API did not answer.");
  }
}

export async function clearFocusAction(
  clientId: string,
  slug: string,
  month: string,
): Promise<FocusActionResult> {
  try {
    await apiFetch(`/v2/focus/${month}`, { method: "DELETE", clientId });
    revalidatePath(`/${slug}/focus`);
    return { ok: true };
  } catch (error) {
    return failure(error, "The focus could not be cleared: the API did not answer.");
  }
}
