import { cookies } from "next/headers";

import { apiFetch, type Client } from "@/lib/api";
import { defaultDateRange } from "@/lib/dates";

export async function resolveClientId(
  searchParams?: Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined>,
): Promise<string | null> {
  const params = searchParams instanceof Promise ? await searchParams : searchParams;
  const fromQuery = typeof params?.clientId === "string" ? params.clientId : null;
  if (fromQuery) return fromQuery;

  const cookieStore = await cookies();
  const fromCookie = cookieStore.get("oiq_client_id")?.value;
  if (fromCookie) return fromCookie;

  // Match the chrome default: first accessible client when none is persisted yet.
  try {
    const clients = await apiFetch<Client[]>("/clients");
    return clients[0]?.id ?? null;
  } catch {
    return null;
  }
}

export async function resolveDateRange(
  searchParams?: Promise<Record<string, string | string[] | undefined>> | Record<string, string | string[] | undefined>,
): Promise<{ from: string; to: string }> {
  const params = searchParams instanceof Promise ? await searchParams : searchParams;
  const fromQuery = typeof params?.from === "string" ? params.from : null;
  const toQuery = typeof params?.to === "string" ? params.to : null;
  if (fromQuery && toQuery) {
    return { from: fromQuery, to: toQuery };
  }

  const cookieStore = await cookies();
  const fromCookie = cookieStore.get("oiq_from")?.value;
  const toCookie = cookieStore.get("oiq_to")?.value;
  if (fromCookie && toCookie) {
    return { from: fromCookie, to: toCookie };
  }

  return defaultDateRange(30);
}

export async function loadClientById(clientId: string): Promise<Client | null> {
  try {
    const clients = await apiFetch<Client[]>("/clients");
    return clients.find((client) => client.id === clientId) ?? null;
  } catch {
    return null;
  }
}
