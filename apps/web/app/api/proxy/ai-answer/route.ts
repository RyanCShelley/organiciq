import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** What the model said for one prompt. Fetched on open, never synced. */
export async function GET(request: Request) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }
  const url = new URL(request.url);
  const clientId = url.searchParams.get("clientId");
  const promptId = url.searchParams.get("promptId");
  if (!clientId || !promptId) {
    return NextResponse.json({ detail: "clientId and promptId required" }, { status: 400 });
  }
  const res = await fetch(
    `${API_URL}/watch-list/ai/answer?prompt_id=${encodeURIComponent(promptId)}`,
    {
      headers: {
        "Content-Type": "application/json",
        ...authHeaders,
        "X-OrganicIQ-Client-Id": clientId,
      },
    },
  );
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
