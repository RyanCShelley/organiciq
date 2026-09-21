import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { AppShell } from "@/components/layout/AppShell";
import { ContentContainer } from "@/components/ui/ContentContainer";
import { apiFetch, type Client } from "@/lib/api";
import { auth } from "@/lib/auth";
import { resolveStoredRange } from "@/lib/date-range";

import { signOutAction } from "./actions";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await auth();
  if (!session) {
    redirect("/login");
  }

  const cookieStore = await cookies();
  // Same resolution the pages use, so the toolbar shows the window the data came from.
  const ranges = resolveStoredRange(
    cookieStore.get("oiq_range")?.value,
    cookieStore.get("oiq_from")?.value,
    cookieStore.get("oiq_to")?.value,
  );

  let clients: Client[] = [];
  try {
    clients = await apiFetch<Client[]>("/clients");
  } catch {
    clients = [];
  }

  const selectedClientId = cookieStore.get("oiq_client_id")?.value || clients[0]?.id || "";
  const from = ranges.from;
  const to = ranges.to;

  return (
    <AppShell
      clients={clients}
      clientId={selectedClientId}
      from={from}
      to={to}
      userEmail={session.user?.email}
      signOutAction={signOutAction}
    >
      <ContentContainer>{children}</ContentContainer>
    </AppShell>
  );
}
