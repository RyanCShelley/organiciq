"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

export type ClientTeamMember = {
  user_id: string;
  email: string;
  name: string | null;
  role: string;
  is_active: boolean;
  /** Access comes from the admin role rather than a per-client assignment. */
  via_admin: boolean;
};

function friendlyError(e: unknown, fallback: string): string {
  const message = e instanceof Error ? e.message : fallback;
  if (message.includes("403") || message.toLowerCase().includes("admin access required")) {
    return "Only an SMA admin can change client access.";
  }
  return message;
}

export async function assignClientAccessAction(clientId: string, userId: string) {
  if (!clientId || !userId) {
    return { ok: false as const, error: "Missing client or person" };
  }
  try {
    await apiFetch("/admin/user-clients", {
      method: "POST",
      clientId,
      body: { user_id: userId, client_id: clientId, role: "sma_team" },
    });
    revalidatePath("/clients", "layout");
    return { ok: true as const };
  } catch (e) {
    return { ok: false as const, error: friendlyError(e, "Failed to grant access") };
  }
}

export async function removeClientAccessAction(clientId: string, userId: string) {
  if (!clientId || !userId) {
    return { ok: false as const, error: "Missing client or person" };
  }
  try {
    await apiFetch("/admin/user-clients", {
      method: "DELETE",
      clientId,
      body: { user_id: userId, client_id: clientId },
    });
    revalidatePath("/clients", "layout");
    return { ok: true as const };
  } catch (e) {
    return { ok: false as const, error: friendlyError(e, "Failed to remove access") };
  }
}
