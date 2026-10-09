"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

export type KeywordTargetEntry = {
  keyword: string;
  target_url: string | null;
  /** primary | secondary | null. Null means nobody has said yet. */
  term_role: "primary" | "secondary" | null;
  group_name: string | null;
  priority: boolean;
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
  const role = String(formData.get("term_role") || "").trim();
  const entry: KeywordTargetEntry = {
    keyword,
    target_url: String(formData.get("target_url") || "").trim() || null,
    term_role: role === "primary" || role === "secondary" ? role : null,
    group_name: String(formData.get("group_name") || "").trim() || null,
    priority: String(formData.get("priority") || "") === "true",
    note: String(formData.get("note") || "").trim() || null,
  };

  try {
    await apiFetch("/decisions/keyword-page-map", {
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
