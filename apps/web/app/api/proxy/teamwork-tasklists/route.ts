import { getProxyAuthHeaders } from "@/lib/proxy-auth";
import { NextResponse } from "next/server";

const API_URL = process.env.API_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** The tasklists the install's token can see. Portfolio-wide, not per client. */
export async function GET() {
  const authHeaders = await getProxyAuthHeaders();
  if (!authHeaders) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }
  const res = await fetch(`${API_URL}/decisions/teamwork/tasklists`, {
    headers: { "Content-Type": "application/json", ...authHeaders },
  });
  const text = await res.text();
  return new NextResponse(text, {
    status: res.status,
    headers: { "Content-Type": res.headers.get("Content-Type") || "application/json" },
  });
}
