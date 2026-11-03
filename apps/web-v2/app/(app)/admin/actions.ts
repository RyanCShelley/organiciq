"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { DeletePreview, PullStatus } from "@/lib/admin";

type Result<T> = { ok: true; value: T } | { ok: false; error: string };

function failure(error: unknown, fallback: string): { ok: false; error: string } {
  return { ok: false, error: error instanceof ApiError ? error.message : fallback };
}

export async function deletePreviewAction(clientId: string): Promise<Result<DeletePreview>> {
  try {
    return { ok: true, value: await apiFetch<DeletePreview>(`/v2/admin/clients/${clientId}/delete-preview`) };
  } catch (error) {
    return failure(error, "The preview could not be loaded: the API did not answer.");
  }
}

export async function deleteClientAction(clientId: string, confirmName: string): Promise<Result<{ deleted: string; rows: number }>> {
  try {
    const value = await apiFetch<{ deleted: string; rows: number; tables: number }>(`/v2/admin/clients/${clientId}`, {
      method: "DELETE",
      body: { confirm_name: confirmName },
    });
    return { ok: true, value };
  } catch (error) {
    return failure(error, "The client could not be deleted: the API did not answer.");
  }
}

export async function pullStatusAction(clientId: string): Promise<Result<PullStatus>> {
  try {
    return { ok: true, value: await apiFetch<PullStatus>(`/v2/admin/clients/${clientId}/pull`) };
  } catch (error) {
    return failure(error, "The pull status could not be loaded: the API did not answer.");
  }
}

export async function startPullAction(clientId: string, force = false): Promise<Result<PullStatus>> {
  try {
    return { ok: true, value: await apiFetch<PullStatus>(`/v2/admin/clients/${clientId}/pull${force ? "?force=true" : ""}`, { method: "POST" }) };
  } catch (error) {
    return failure(error, "The pull could not be started: the API did not answer.");
  }
}

export async function stopPullAction(clientId: string): Promise<Result<PullStatus>> {
  try {
    return { ok: true, value: await apiFetch<PullStatus>(`/v2/admin/clients/${clientId}/pull/stop`, { method: "POST" }) };
  } catch (error) {
    return failure(error, "The pull could not be stopped: the API did not answer.");
  }
}

export async function setGscLeanAction(clientId: string, enabled: boolean): Promise<Result<{ gsc_lean: boolean; queued: string[] }>> {
  try {
    return { ok: true, value: await apiFetch(`/v2/admin/clients/${clientId}/gsc-lean`, { method: "POST", body: { enabled } }) };
  } catch (error) {
    return failure(error, "The Search Console pull could not be switched: the API did not answer.");
  }
}

export async function setGscLeanAllAction(): Promise<Result<{ switched: number }>> {
  try {
    return { ok: true, value: await apiFetch("/v2/admin/clients/gsc-lean-all", { method: "POST" }) };
  } catch (error) {
    return failure(error, "The clients could not be switched: the API did not answer.");
  }
}
