"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { AskDepth, AskItem } from "@/lib/bi";

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

export async function askAction(
  clientId: string,
  question: string,
  depth: AskDepth,
  history: { role: "user" | "assistant"; content: string }[],
): Promise<{ ok: true; id: string } | { ok: false; error: string }> {
  try {
    const r = await apiFetch<{ id: string }>("/v2/ask", { method: "POST", clientId, body: { question, depth, history } });
    return { ok: true, id: r.id };
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The question could not be sent: the API did not answer." };
  }
}

export async function askStatusAction(clientId: string, id: string): Promise<{ ok: true; item: AskItem; left_usd: number } | { ok: false; error: string }> {
  try {
    const r = await apiFetch<AskItem & { spend: { left_usd: number } }>(`/v2/ask/${id}`, { clientId });
    return { ok: true, item: r, left_usd: r.spend.left_usd };
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The answer could not be read: the API did not answer." };
  }
}
