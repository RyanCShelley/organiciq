import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

// Embedding a few hundred pages takes tens of seconds; the platform default
// would cut the request off and report it as a failure.
export const maxDuration = 60;

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Match terms to pages by subject. Tens of seconds on a large site. */
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
  const res = await fetch(`${API_URL}/decisions/keyword-suggestions/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      "X-OrganicIQ-Client-Id": clientId,
    },
    // The model runs in-process and a large site takes a while; the default
    // would give up before it finishes and look like a failure.
    signal: AbortSignal.timeout(55_000),
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
