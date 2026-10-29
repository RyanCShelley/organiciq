"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { DiagnoseResult, Diagnosis } from "@/lib/engine";

export async function diagnoseAction(
  clientId: string,
  selections: { search: string; page: string }[],
): Promise<DiagnoseResult> {
  try {
    const body = await apiFetch<{ results: Diagnosis[] }>("/v2/engine/diagnose", {
      method: "POST",
      clientId,
      body: { selections },
    });
    return { ok: true, results: body.results };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "The pages could not be read: the API did not answer.",
    };
  }
}
