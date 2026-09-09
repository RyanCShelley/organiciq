import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function DELETE(
  request: Request,
  context: { params: Promise<{ definitionId: string }> },
) {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const { definitionId } = await context.params;
  const clientId = new URL(request.url).searchParams.get("clientId");
  if (!clientId) {
    return NextResponse.json({ detail: "clientId required" }, { status: 400 });
  }

  const res = await fetch(`${API_URL}/admin/conversion-definitions/${definitionId}`, {
    method: "DELETE",
    headers: {
      ...authHeaders,
      "X-OrganicIQ-Client-Id": clientId,
    },
  });

  if (res.status === 204) {
    return new NextResponse(null, { status: 204 });
  }

  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
