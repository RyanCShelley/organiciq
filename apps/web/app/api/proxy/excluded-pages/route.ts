import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Replace the whole list, because that is how the panel edits it. */
export async function PUT(request: Request) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }
  const body = await request.json();
  const clientId = body.clientId as string | undefined;
  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }
  const res = await fetch(`${API_URL}/decisions/excluded-pages`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      "X-OrganicIQ-Client-Id": clientId,
    },
    body: JSON.stringify(body.pages ?? []),
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
