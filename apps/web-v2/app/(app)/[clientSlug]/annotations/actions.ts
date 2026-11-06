"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { Entry } from "@/lib/annotations";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (error: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export async function addNoteAction(clientId: string, date: string, description: string, page: string): Promise<R<true>> {
  try {
    await apiFetch("/v2/annotations", { method: "POST", clientId, body: { date, description, page: page.trim() || null } });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "The note could not be added: the API did not answer.");
  }
}

export async function editEntryAction(clientId: string, id: string, patch: { notes?: string; result?: Entry["result"] }): Promise<R<Entry>> {
  try {
    return { ok: true, value: await apiFetch<Entry>(`/v2/annotations/${id}`, { method: "PATCH", clientId, body: patch }) };
  } catch (e) {
    return fail(e, "The entry could not be saved: the API did not answer.");
  }
}

export async function removeEntryAction(clientId: string, id: string): Promise<R<true>> {
  try {
    await apiFetch(`/v2/annotations/${id}`, { method: "DELETE", clientId });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "The note could not be removed: the API did not answer.");
  }
}
