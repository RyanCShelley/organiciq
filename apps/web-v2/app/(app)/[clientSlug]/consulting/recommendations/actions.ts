"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { Rec, RecState } from "@/lib/portal";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (e: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: e instanceof ApiError ? e.message : fallback });
const touch = (slug: string) => revalidatePath(`/${slug}/consulting`, "layout");
const base = (id?: string) => `/v2/consulting/recommendations${id ? `/${id}` : ""}`;

export async function createRecAction(clientId: string, slug: string, fields: Record<string, unknown>): Promise<R<Rec>> {
  try {
    const value = await apiFetch<Rec>(base(), { method: "POST", clientId, body: fields });
    touch(slug);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not create the brief: the API did not answer.");
  }
}

export async function saveRecAction(clientId: string, slug: string, id: string, revision: number, fields: Record<string, unknown>): Promise<R<Rec>> {
  try {
    const value = await apiFetch<Rec>(base(id), { method: "PATCH", clientId, body: { ...fields, revision } });
    touch(slug);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not save: the API did not answer.");
  }
}

export async function moveRecAction(clientId: string, slug: string, id: string, to: RecState): Promise<R<Rec>> {
  try {
    const value = await apiFetch<Rec>(`${base(id)}/state`, { method: "POST", clientId, body: { to } });
    touch(slug);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not move the brief: the API did not answer.");
  }
}

export async function progressRecAction(clientId: string, slug: string, id: string, body: Record<string, unknown>): Promise<R<Rec>> {
  try {
    const value = await apiFetch<Rec>(`${base(id)}/progress`, { method: "POST", clientId, body });
    touch(slug);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not record that: the API did not answer.");
  }
}

export async function verifyRecAction(clientId: string, slug: string, id: string, state: string, how: string): Promise<R<Rec>> {
  try {
    const value = await apiFetch<Rec>(`${base(id)}/verify`, { method: "POST", clientId, body: { state, how } });
    touch(slug);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not record that: the API did not answer.");
  }
}

export async function followUpRecAction(clientId: string, slug: string, id: string, note: string): Promise<R<Rec>> {
  try {
    const value = await apiFetch<Rec>(`${base(id)}/follow-up`, { method: "POST", clientId, body: { note } });
    touch(slug);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not record that: the API did not answer.");
  }
}
