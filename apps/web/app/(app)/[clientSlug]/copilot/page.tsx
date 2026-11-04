import { CopilotChat } from "@/components/Copilot/CopilotChat";
import { requireAccountClient } from "@/lib/account-routes.server";

// A model turn can run several lookups; the server action inherits this.
export const maxDuration = 120;

export default async function CopilotPage({
  params,
}: {
  params: Promise<{ clientSlug: string }>;
}) {
  const { clientSlug } = await params;
  const client = await requireAccountClient(clientSlug, "copilot");

  return (
    <section>
      <CopilotChat clientId={client.id} clientName={client.client_name} />
    </section>
  );
}
