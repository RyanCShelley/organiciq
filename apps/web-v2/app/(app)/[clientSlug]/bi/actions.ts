"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";

type Result = { ok: true } | { ok: false; error: string };

const fail = (error: unknown, fallback: string): Result => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export async function addChangeAction(clientId: string, slug: string, date: string, description: string, page: string): Promise<Result> {
  try {
    await apiFetch("/v2/bi/changes", { method: "POST", clientId, body: { date, description, page: page.trim() || null } });
    revalidatePath(`/${slug}/bi`);
    return { ok: true };
  } catch (error) {
    return fail(error, "The note could not be saved: the API did not answer.");
  }
}

export async function removeChangeAction(clientId: string, slug: string, id: string): Promise<Result> {
  try {
    await apiFetch(`/v2/bi/changes/${id}`, { method: "DELETE", clientId });
    revalidatePath(`/${slug}/bi`);
    return { ok: true };
  } catch (error) {
    return fail(error, "The note could not be removed: the API did not answer.");
  }
}
