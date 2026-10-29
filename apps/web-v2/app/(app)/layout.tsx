import { redirect } from "next/navigation";

import { V2Shell } from "@/components/layout/V2Shell";
import { auth } from "@/lib/auth";
import { getClients } from "@/lib/clients";

import { signOutAction } from "./actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) redirect("/login");

  const clients = await getClients().catch(() => []);

  return (
    <V2Shell clients={clients} userEmail={session.user?.email} signOutAction={signOutAction}>
      {children}
    </V2Shell>
  );
}
