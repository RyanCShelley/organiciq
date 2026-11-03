import { redirect } from "next/navigation";

import { V2Shell } from "@/components/layout/V2Shell";
import { auth } from "@/lib/auth";
import { apiFetch } from "@/lib/api";
import { getClients } from "@/lib/clients";

import { signOutAction } from "./actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) redirect("/login");

  // Independent calls: asked together, the page waits for the slower, not for both.
  const [clients, me] = await Promise.all([
    getClients().catch(() => []),
    apiFetch<{ role: string }>("/auth/me").catch(() => null),
  ]);

  return (
    <V2Shell clients={clients} userEmail={session.user?.email} isAdmin={me?.role === "sma_admin"} signOutAction={signOutAction}>
      {children}
    </V2Shell>
  );
}
