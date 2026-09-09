"use server";

import { cookies } from "next/headers";
import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

export async function deleteClientAction(formData: FormData) {
  const clientId = String(formData.get("clientId") || "").trim();
  const clientName = String(formData.get("clientName") || "").trim();
  if (!clientId) {
    return { ok: false as const, error: "Missing client" };
  }

  try {
    await apiFetch(`/clients/${clientId}`, { method: "DELETE" });
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : `Failed to delete ${clientName || "client"}`,
    };
  }

  const cookieStore = await cookies();
  if (cookieStore.get("oiq_client_id")?.value === clientId) {
    cookieStore.delete("oiq_client_id");
  }

  revalidatePath("/clients");
  revalidatePath("/platform");
  revalidatePath("/dashboard");
  return { ok: true as const };
}
