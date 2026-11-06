"use server";

import { ApiError, apiFetch } from "@/lib/api";
import { revalidatePath } from "next/cache";

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

export async function teamAssignAction(userIds: string[], clientIds: string[]): Promise<Result<{ added: number; already: number; admins_skipped: number }>> {
  try {
    const value = await apiFetch<{ added: number; already: number; admins_skipped: number }>("/v2/admin/team-access/assign", { method: "POST", body: { user_ids: userIds, client_ids: clientIds } });
    revalidatePath("/admin");
    return { ok: true, value };
  } catch (error) {
    return failure(error, "Access could not be given: the API did not answer.");
  }
}

export async function teamRemoveAction(userIds: string[], clientIds: string[]): Promise<Result<{ removed: number; admins_skipped: number }>> {
  try {
    const value = await apiFetch<{ removed: number; admins_skipped: number }>("/v2/admin/team-access/remove", { method: "POST", body: { user_ids: userIds, client_ids: clientIds } });
    revalidatePath("/admin");
    return { ok: true, value };
  } catch (error) {
    return failure(error, "Access could not be removed: the API did not answer.");
  }
}

export async function addPersonAction(
  email: string,
  name: string,
  role: "sma_team" | "sma_admin",
): Promise<Result<{ outcome: "added" | "restored"; id: string; email: string; emailed: boolean }>> {
  try {
    const value = await apiFetch<{ outcome: "added" | "restored"; id: string; email: string; emailed: boolean }>("/v2/admin/team-access/people", { method: "POST", body: { email, name: name.trim() || null, role } });
    revalidatePath("/admin");
    return { ok: true, value };
  } catch (error) {
    return failure(error, "That person could not be added.");
  }
}

export async function removePeopleAction(userIds: string[]): Promise<Result<{ removed: number }>> {
  try {
    const value = await apiFetch<{ removed: number }>("/v2/admin/team-access/people/remove", { method: "POST", body: { user_ids: userIds } });
    revalidatePath("/admin");
    return { ok: true, value };
  } catch (error) {
    return failure(error, "They could not be removed: the API did not answer.");
  }
}

export async function restorePeopleAction(userIds: string[]): Promise<Result<{ restored: number }>> {
  try {
    const value = await apiFetch<{ restored: number }>("/v2/admin/team-access/people/restore", { method: "POST", body: { user_ids: userIds } });
    revalidatePath("/admin");
    return { ok: true, value };
  } catch (error) {
    return failure(error, "They could not be restored: the API did not answer.");
  }
}

export async function outboundIpAction(): Promise<Result<{ address: string; asked: string; user_agent: string }>> {
  try {
    return { ok: true, value: await apiFetch<{ address: string; asked: string; user_agent: string }>("/v2/admin/outbound-ip") };
  } catch (error) {
    return failure(error, "The address could not be looked up: the API did not answer.");
  }
}
