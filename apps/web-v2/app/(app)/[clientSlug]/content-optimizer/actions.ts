"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { OptDepth, OptKind, OptPage } from "@/lib/optimizer";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (error: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export async function optimizerPageAction(clientId: string, url: string): Promise<R<OptPage>> {
  try {
    return { ok: true, value: await apiFetch<OptPage>(`/v2/optimizer/page?${new URLSearchParams({ url })}`, { clientId }) };
  } catch (e) {
    return fail(e, "The page could not be read: the API did not answer.");
  }
}

export async function optimizerDraftAction(clientId: string, url: string, kind: OptKind, depth: OptDepth): Promise<R<true>> {
  try {
    await apiFetch("/v2/optimizer/draft", { method: "POST", clientId, body: { url, kind, depth } });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "The change could not be requested: the API did not answer.");
  }
}
