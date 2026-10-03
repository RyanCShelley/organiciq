"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

export type KeywordMapEntry = {
  keyword: string;
  page_url: string | null;
  note: string | null;
};

/**
 * Save the mapping for one keyword.
 *
 * Saved one row at a time on purpose. A single Save button over fifty
 * keywords means nobody fills any of them in: the work is done a term at a
 * time, between other things, and a form that loses half of it on a reload
 * is a form that stays empty.
 */
export async function saveKeywordPageMapAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  const clientSlug = String(formData.get("clientSlug") || "");
  const keyword = String(formData.get("keyword") || "").trim();
  if (!clientId || !keyword) {
    return { ok: false as const, error: "Missing client or keyword." };
  }

  // An empty page URL is a decision — "no page owns this yet" — and the
  // engine treats it as an answer rather than a gap. That is only true if
  // the row is written, so this does not bail out on a blank.
  const entry: KeywordMapEntry = {
    keyword,
    page_url: String(formData.get("page_url") || "").trim() || null,
    note: String(formData.get("note") || "").trim() || null,
  };

  try {
    await apiFetch("/keyword-page-map", {
      method: "PUT",
      clientId,
      body: { entries: [entry] },
    });
  } catch (error) {
    return {
      ok: false as const,
      error: error instanceof Error ? error.message : "Could not save.",
    };
  }

  if (clientSlug) revalidatePath(`/${clientSlug}/keyword-map`);
  return { ok: true as const };
}
