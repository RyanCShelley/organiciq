"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch } from "@/lib/api";
import type { StaffReport } from "@/lib/portal";

type R = { ok: true; value: StaffReport } | { ok: false; error: string };
const fail = (e: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: e instanceof ApiError ? e.message : fallback });

export async function saveReportAction(clientId: string, slug: string, month: string, body: { analysis: string; title: string; revision: number | null }): Promise<R> {
  try {
    const value = await apiFetch<StaffReport>("/v2/consulting/report", { method: "PUT", clientId, body: { month, ...body } });
    revalidatePath(`/${slug}/consulting/report`);
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not save: the API did not answer.");
  }
}

export async function moveReportAction(clientId: string, slug: string, month: string, to: "published" | "draft"): Promise<R> {
  try {
    const value = await apiFetch<StaffReport>("/v2/consulting/report/state", { method: "POST", clientId, body: { month, to } });
    revalidatePath(`/${slug}/consulting/report`);
    revalidatePath(`/consulting/${slug}`, "layout");
    return { ok: true, value };
  } catch (e) {
    return fail(e, "Could not change that: the API did not answer.");
  }
}
