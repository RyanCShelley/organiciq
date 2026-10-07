"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

export async function createAnnotationAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  if (!clientId) return { ok: false as const, error: "Missing client" };

  const body = {
    date: String(formData.get("date") || ""),
    annotation_type: String(formData.get("annotation_type") || "manual_note"),
    growth_action: String(formData.get("growth_action") || "").trim() || null,
    description: String(formData.get("description") || "").trim(),
    page_url: String(formData.get("page_url") || "").trim() || null,
    success_metric: String(formData.get("success_metric") || "").trim() || null,
    completed_at: String(formData.get("completed_at") || "").trim() || null,
    measurement_start_date: String(formData.get("measurement_start_date") || "").trim() || null,
    measurement_end_date: String(formData.get("measurement_end_date") || "").trim() || null,
    notes: String(formData.get("notes") || "").trim() || null,
    result: String(formData.get("result") || "not_yet_measured"),
  };

  if (!body.date || !body.description) {
    return { ok: false as const, error: "Date and description are required." };
  }

  try {
    await apiFetch("/annotations", { method: "POST", clientId, body });
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Failed to create annotation",
    };
  }

  revalidatePath("/annotations");
  return { ok: true as const };
}

export async function importAnnotationsAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  const csvText = String(formData.get("csv_text") || "");
  if (!clientId) return { ok: false as const, error: "Missing client" };
  if (!csvText.trim()) return { ok: false as const, error: "Paste or upload CSV content." };

  try {
    const result = await apiFetch<{ created: number; errors: Array<{ row: number; error: string }> }>(
      "/annotations/import",
      {
        method: "POST",
        clientId,
        body: { csv_text: csvText },
      },
    );
    revalidatePath("/annotations");
    return { ok: true as const, ...result };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "Import failed",
    };
  }
}

export async function remeasureAnnotationsAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "");
  if (!clientId) return;
  await apiFetch("/annotations/remeasure", { method: "POST", clientId, body: {} });
  revalidatePath("/annotations");
}

