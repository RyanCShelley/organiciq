"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { CtrDepth, CtrDetail } from "@/lib/ctr";

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

export async function ctrTitleAction(clientId: string, url: string, from: string, to: string, depth: CtrDepth): Promise<R<true>> {
  try {
    await apiFetch("/v2/ctr/title", { method: "POST", clientId, body: { url, from, to, depth } });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "The title options could not be requested: the API did not answer.");
  }
}
