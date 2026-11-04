"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (error: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export async function verifyInlinkAction(clientId: string, source: string, target: string): Promise<R<{ found: boolean; anchor: string | null; checked: boolean; error: string | null }>> {
  try {
    return { ok: true, value: await apiFetch("/v2/inlinks/verify", { method: "POST", clientId, body: { source, target } }) };
  } catch (e) {
    return fail(e, "The page could not be checked: the API did not answer.");
  }
}

export async function ignoreInlinkAction(clientId: string, slug: string, target: string, source: string | null): Promise<R<true>> {
  try {
    await apiFetch("/v2/inlinks/ignore", { method: "POST", clientId, body: { target, source } });
    revalidatePath(`/${slug}/inlinks`);
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "That could not be ignored: the API did not answer.");
  }
}

export async function restoreInlinkAction(clientId: string, slug: string, id: string): Promise<R<true>> {
  try {
    await apiFetch(`/v2/inlinks/ignore/${id}`, { method: "DELETE", clientId });
    revalidatePath(`/${slug}/inlinks`);
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "That could not be restored: the API did not answer.");
  }
}
