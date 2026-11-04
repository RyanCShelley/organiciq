"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { ImportReport, ImportResult } from "@/lib/watchlist";

export async function importWatchlistAction(
  clientId: string,
  slug: string,
  csvText: string,
  dryRun: boolean,
): Promise<ImportResult> {
  if (!clientId || !csvText.trim()) return { ok: false, error: "Choose a CSV file first." };
  try {
    const report = await apiFetch<ImportReport>("/v2/watchlist/import", {
      method: "POST",
      clientId,
      body: { csv_text: csvText, dry_run: dryRun },
    });
    if (!dryRun) revalidatePath(`/${slug}/watchlist`);
    return { ok: true, report };
  } catch (error) {
    if (error instanceof ApiError) return { ok: false, error: error.message };
    return { ok: false, error: "The import could not reach the API." };
  }
}
