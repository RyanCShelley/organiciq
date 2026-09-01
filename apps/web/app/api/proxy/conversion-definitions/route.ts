import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

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

  const res = await fetch(`${API_URL}/admin/conversion-definitions`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders,
      "X-OrganicIQ-Client-Id": clientId,
    },
    body: JSON.stringify({
      event_name: body.event_name,
      conversion_name: body.conversion_name,
      conversion_type: body.conversion_type ?? "lead",
      is_primary: Boolean(body.is_primary),
      active: body.active !== false,
    }),
  });

  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
