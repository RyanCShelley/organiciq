"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { CtrDetail } from "@/lib/ctr";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (error: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export async function ctrPageAction(clientId: string, url: string, from: string, to: string): Promise<R<CtrDetail>> {
  try {
    const q = new URLSearchParams({ url, from, to });
    return { ok: true, value: await apiFetch<CtrDetail>(`/v2/ctr/page?${q}`, { clientId }) };
  } catch (e) {
    return fail(e, "The page could not be read: the API did not answer.");
  }
}

export async function ctrToPlanAction(clientId: string, url: string, from: string, to: string): Promise<R<{ created: boolean }>> {
  try {
    const r = await apiFetch<{ created: boolean }>("/v2/ctr/plan", { method: "POST", clientId, body: { url, from, to } });
    return { ok: true, value: r };
  } catch (e) {
    return fail(e, "The page could not be sent to the plan: the API did not answer.");
  }
}
