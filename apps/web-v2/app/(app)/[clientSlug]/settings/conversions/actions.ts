"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { ActionResult } from "@/lib/client-settings";
import type {
  CompletionPattern,
  ConversionDefinition,
  ConversionPage,
  Ga4Page,
  Ga4PagesResult,
  SuggestedPattern,
  TrackedSummary,
} from "@/lib/conversions";

function failure(error: unknown): ActionResult {
  return {
    ok: false,
    error: error instanceof ApiError ? error.message : "Could not save: the API did not answer.",
  };
}

export async function saveConversionDefinitionsAction(
  clientId: string,
  slug: string,
  definitions: ConversionDefinition[],
): Promise<ActionResult> {
  try {
    await apiFetch("/admin/conversion-definitions", { method: "PUT", clientId, body: definitions });
    revalidatePath(`/${slug}/settings/conversions`);
    return { ok: true };
  } catch (error) {
    return failure(error);
  }
}

export async function saveConversionPagesAction(
  clientId: string,
  slug: string,
  pages: ConversionPage[],
): Promise<ActionResult> {
  try {
    await apiFetch("/admin/conversion-pages", { method: "PUT", clientId, body: pages });
    revalidatePath(`/${slug}/settings/conversions`);
    return { ok: true };
  } catch (error) {
    return failure(error);
  }
}

export async function loadGa4PagesAction(
  clientId: string,
  events: string[],
  days: number,
): Promise<Ga4PagesResult> {
  if (events.length === 0) return { ok: false, error: "Choose at least one event." };
  try {
    const query = events.map((e) => `event=${encodeURIComponent(e)}`).join("&");
    const body = await apiFetch<{
      pages: Ga4Page[];
      suggested: SuggestedPattern[];
      tracked: TrackedSummary[];
      pages_not_shown: number;
    }>(
      `/v2/conversions/pages?${query}&days=${days}`,
      { clientId },
    );
    return {
      ok: true,
      pages: body.pages,
      suggested: body.suggested,
      tracked: body.tracked,
      notShown: body.pages_not_shown,
    };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "GA4 did not answer.",
    };
  }
}

export async function saveCompletionPatternsAction(
  clientId: string,
  slug: string,
  patterns: CompletionPattern[],
): Promise<ActionResult> {
  try {
    await apiFetch("/v2/conversions/completion-patterns", { method: "PUT", clientId, body: patterns });
    revalidatePath(`/${slug}/settings/conversions`);
    return { ok: true };
  } catch (error) {
    return failure(error);
  }
}
