"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { ActionResult } from "@/lib/client-settings";

function failure(error: unknown, fallback: string): ActionResult {
  return { ok: false, error: error instanceof ApiError ? error.message : fallback };
}

/** Save some fields of the client record. Only the fields sent change. */
export async function updateClientAction(
  clientId: string,
  slug: string,
  fields: Record<string, unknown>,
): Promise<ActionResult> {
  try {
    await apiFetch(`/clients/${clientId}`, { method: "PATCH", body: fields });
    revalidatePath(`/${slug}`, "layout");
    return { ok: true };
  } catch (error) {
    return failure(error, "Could not save: the API did not answer.");
  }
}

export async function assignUserAction(
  clientId: string,
  slug: string,
  userId: string,
): Promise<ActionResult> {
  try {
    await apiFetch("/admin/user-clients", {
      method: "POST",
      body: { user_id: userId, client_id: clientId },
    });
    revalidatePath(`/${slug}/settings/team`);
    return { ok: true };
  } catch (error) {
    return failure(error, "Could not add that person: the API did not answer.");
  }
}

export async function unassignUserAction(
  clientId: string,
  slug: string,
  userId: string,
): Promise<ActionResult> {
  try {
    await apiFetch("/admin/user-clients", {
      method: "DELETE",
      body: { user_id: userId, client_id: clientId },
    });
    revalidatePath(`/${slug}/settings/team`);
    return { ok: true };
  } catch (error) {
    return failure(error, "Could not remove that person: the API did not answer.");
  }
}
