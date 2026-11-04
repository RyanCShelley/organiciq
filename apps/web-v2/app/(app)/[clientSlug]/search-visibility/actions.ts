"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { SvDetail } from "@/lib/search-visibility";

export async function termDetailAction(clientId: string, term: string, from: string, to: string): Promise<{ ok: true; detail: SvDetail } | { ok: false; error: string }> {
  try {
    const q = new URLSearchParams({ term, from, to });
    return { ok: true, detail: await apiFetch<SvDetail>(`/v2/search-visibility/term?${q}`, { clientId }) };
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The term could not be read: the API did not answer." };
  }
}
