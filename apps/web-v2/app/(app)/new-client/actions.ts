"use server";

import { revalidatePath } from "next/cache";

import { ApiError, apiFetch, type Client } from "@/lib/api";

export type CreateResult = { ok: true; slug: string } | { ok: false; error: string };

export async function createClientAction(fields: Record<string, unknown>): Promise<CreateResult> {
  try {
    const created = await apiFetch<Client>("/clients", { method: "POST", body: fields });
    revalidatePath("/", "layout");
    return { ok: true, slug: created.slug };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "Could not add the client: the API did not answer.",
    };
  }
}
