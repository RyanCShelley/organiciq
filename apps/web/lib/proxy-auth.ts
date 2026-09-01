import { auth, ensureApiAccessToken } from "@/lib/auth";

export async function getProxyAuthHeaders(): Promise<Record<string, string> | null> {
  const session = await auth();
  const accessToken = await ensureApiAccessToken(session);
  if (!accessToken) return null;
  return { Authorization: `Bearer ${accessToken}` };
}
