import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function forward(
  path: string,
  method: string,
  clientId: string,
  body?: unknown,
) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }
  const res = await fetch(`${API_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      "X-OrganicIQ-Client-Id": clientId,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}

/** Confirm the stages somebody agreed to. Only these are read by the engine. */
export async function PUT(request: Request) {
  const body = await request.json();
  const clientId = body.clientId as string | undefined;
  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }
  return forward("/decisions/page-stages", "PUT", clientId, body.stages ?? []);
}

/** Ask the model to read the pages and propose a stage for each. */
export async function POST(request: Request) {
  const body = await request.json();
  const clientId = body.clientId as string | undefined;
  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }
  return forward("/decisions/page-stages/suggest", "POST", clientId);
}
