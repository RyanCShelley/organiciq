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

/** Save what was done with one link, or the link text chosen for it. The screen already shows the change, so nothing is re-read. */
export async function setInlinkStateAction(clientId: string, source: string, target: string, change: { status?: "todo" | "added" | "skipped"; anchor?: string }): Promise<R<{ status: string; anchor: string | null }>> {
  try {
    return { ok: true, value: await apiFetch("/v2/inlinks/state", { method: "POST", clientId, body: { source, target, ...change } }) };
  } catch (e) {
    return fail(e, "That could not be saved: the API did not answer.");
  }
}

/** Have the sentence that carries this link written around the chosen link text. It is kept on the link for the whole team. */
export async function writeInlinkSentenceAction(clientId: string, source: string, target: string, anchor: string): Promise<R<{ ok: true; sentence: string; anchor: string } | { ok: false; reason: string }>> {
  try {
    return { ok: true, value: await apiFetch("/v2/inlinks/sentence", { method: "POST", clientId, body: { source, target, anchor } }) };
  } catch (e) {
    return fail(e, "The sentence could not be written: the API did not answer.");
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
