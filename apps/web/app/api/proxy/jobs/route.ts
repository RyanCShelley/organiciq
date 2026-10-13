import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function GET(request: Request) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const clientId = new URL(request.url).searchParams.get("clientId");
  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }

  const res = await fetch(`${API_URL}/jobs`, {
    headers: {
      ...authHeaders,
      "X-OrganicIQ-Client-Id": clientId,
    },
    cache: "no-store",
  });

  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}

const JOB_PARAM_KEYS = ["engine", "limit", "source", "page_limit"] as const;

function pickJobParams(raw: unknown): Record<string, string | number> | undefined {
  if (!raw || typeof raw !== "object") return undefined;
  const out: Record<string, string | number> = {};
  for (const key of JOB_PARAM_KEYS) {
    const value = (raw as Record<string, unknown>)[key];
    if (typeof value === "number" && Number.isFinite(value)) out[key] = value;
    else if (typeof value === "string" && value.length <= 64) out[key] = value;
  }
  return Object.keys(out).length ? out : undefined;
}

export async function POST(request: Request) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const body = await request.json();
  const clientId = body.clientId as string | undefined;
  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }

  const res = await fetch(`${API_URL}/jobs`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      "X-OrganicIQ-Client-Id": clientId,
    },
    body: JSON.stringify({
      source: body.source,
      start_date: body.start_date,
      end_date: body.end_date,
      // Only the keys the job handlers read, and only plain strings and
      // numbers. This used to be dropped entirely, so the AI-search job —
      // which refuses to run without an engine — could never be started from
      // the page. The handlers still enforce their own ceilings.
      params: pickJobParams(body.params),
    }),
  });

  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
