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

function optionalText(formData: FormData, key: string): string | undefined {
  const value = String(formData.get(key) || "").trim();
  return value ? value : undefined;
}

function optionalInt(formData: FormData, key: string): number | undefined {
  const value = String(formData.get(key) || "").trim();
  if (!value) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : undefined;
}

/** Strip scheme, www and any path so the domain matches what GSC/GA4 report. */
function normalizeDomain(raw: string): string {
  return raw
    .trim()
    .replace(/^https?:\/\//i, "")
    .replace(/^www\./i, "")
    .replace(/\/.*$/, "")
    .toLowerCase();
}

export async function createClientAction(formData: FormData) {
  const clientName = String(formData.get("client_name") || "").trim();
  const domain = normalizeDomain(String(formData.get("domain") || ""));
  const tierId = String(formData.get("tier_id") || "").trim();

  if (!clientName) return { ok: false as const, error: "Client name is required" };
  if (!domain) return { ok: false as const, error: "Domain is required" };
  if (!tierId) return { ok: false as const, error: "Tier is required" };

  try {
    const created = await apiFetch<{ id: string; slug: string }>("/clients", {
      method: "POST",
      body: {
        client_name: clientName,
        domain,
        tier_id: tierId,
        // The API allocates a unique slug when this is omitted.
        start_date: optionalText(formData, "start_date"),
        primary_market: optionalText(formData, "primary_market"),
        monthly_lead_goal: optionalInt(formData, "monthly_lead_goal"),
        status: optionalText(formData, "status") || "onboarding",
      },
    });

    revalidatePath("/clients");
    revalidatePath("/platform");
    return { ok: true as const, slug: created.slug };
  } catch (e) {
    const message = e instanceof Error ? e.message : "Failed to create client";
    // require_sma_admin guards POST /clients.
    if (message.includes("403") || message.toLowerCase().includes("admin access required")) {
      return {
        ok: false as const,
        error: "Only an SMA admin can add clients. Ask an admin, or add your address to SMA_ADMIN_EMAILS.",
      };
    }
    return { ok: false as const, error: message };
  }
}
