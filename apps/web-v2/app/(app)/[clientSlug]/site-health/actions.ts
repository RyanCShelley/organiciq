"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";

export type CrawlTriggerResult =
  | { ok: true; queued: string[] }
  | { ok: false; error: string };

export async function triggerSiteCrawlAction(clientId: string, slug: string): Promise<CrawlTriggerResult> {
  try {
    const res = await apiFetch<{ queued: string[] }>("/v2/connections/pull", {
      method: "POST",
      clientId,
      body: { sources: ["site_crawl"] },
    });
    revalidatePath(`/${slug}/site-health`);
    return { ok: true, queued: res.queued ?? [] };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "Could not start site crawl: the API did not answer.",
    };
  }
}
