import { redirect } from "next/navigation";

import { auth, ensureApiAccessToken } from "@/lib/auth";

// Same API as the current tool. v2 adds routes to it; it does not have its own.
const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function parseApiErrorBody(text: string): string {
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
    if (Array.isArray(body.detail)) return "Request failed";
  } catch {
    // keep raw text
  }
  return text;
}

export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; clientId?: string | null } = {},
): Promise<T> {
  const session = await auth();
  const accessToken = await ensureApiAccessToken(session);
  const headers: Record<string, string> = { "Content-Type": "application/json" };

  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  if (options.clientId) headers["X-OrganicIQ-Client-Id"] = options.clientId;

  const res = await fetch(`${API_URL}${path}`, {
    method: options.method ?? "GET",
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    if (res.status === 401) redirect("/login?error=SessionExpired");
    throw new ApiError(res.status, parseApiErrorBody(text) || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** The fields of a client that v2 screens read. The API sends more. */
export type Client = {
  id: string;
  client_name: string;
  slug: string;
  domain: string;
  tier_id: string;
  plan_label?: string | null;
  timezone: string;
  account_sheet_url?: string | null;
};
