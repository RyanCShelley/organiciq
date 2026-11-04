"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { ScCandidate, ScConcept, ScDepth, ScIgnoreScope, ScPage } from "@/lib/schema";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (error: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export async function searchConceptsAction(clientId: string, names: string[]): Promise<R<Record<string, ScCandidate[]>>> {
  try {
    const r = await apiFetch<{ candidates: Record<string, ScCandidate[]> }>("/v2/schema/concepts/search", { method: "POST", clientId, body: { names } });
    return { ok: true, value: r.candidates };
  } catch (e) {
    return fail(e, "Wikidata could not be searched: the API did not answer.");
  }
}

export async function approveConceptAction(clientId: string, slug: string, c: { name: string; qid: string; label: string; description: string }): Promise<R<ScConcept>> {
  try {
    const value = await apiFetch<ScConcept>("/v2/schema/concepts", { method: "POST", clientId, body: c });
    revalidatePath(`/${slug}/schema`);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "The concept could not be approved: the API did not answer.");
  }
}

export async function removeConceptAction(clientId: string, slug: string, id: string): Promise<R<true>> {
  try {
    await apiFetch(`/v2/schema/concepts/${id}`, { method: "DELETE", clientId });
    revalidatePath(`/${slug}/schema`);
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "The concept could not be removed: the API did not answer.");
  }
}

export async function pageAction(clientId: string, url: string): Promise<R<ScPage>> {
  try {
    return { ok: true, value: await apiFetch<ScPage>(`/v2/schema/page?url=${encodeURIComponent(url)}`, { clientId }) };
  } catch (e) {
    return fail(e, "The page could not be read: the API did not answer.");
  }
}

export async function startPageReportAction(clientId: string, kind: "audit" | "markup", url: string, depth: ScDepth): Promise<R<true>> {
  try {
    await apiFetch(`/v2/schema/page/${kind}`, { method: "POST", clientId, body: { url, depth } });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "The request could not be sent: the API did not answer.");
  }
}

export async function addIgnoreAction(clientId: string, slug: string, scope: ScIgnoreScope, key: string, label: string): Promise<R<true>> {
  try {
    await apiFetch("/v2/schema/ignores", { method: "POST", clientId, body: { scope, key, label } });
    revalidatePath(`/${slug}/schema`);
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "That could not be ignored: the API did not answer.");
  }
}

export async function removeIgnoreAction(clientId: string, slug: string, id: string): Promise<R<true>> {
  try {
    await apiFetch(`/v2/schema/ignores/${id}`, { method: "DELETE", clientId });
    revalidatePath(`/${slug}/schema`);
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "That could not be restored: the API did not answer.");
  }
}
