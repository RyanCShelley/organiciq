import { BaselineBuilder } from "@/components/Baseline/BaselineBuilder";
import { ClientAccountSection } from "@/components/ClientAccountSection";
import { LeadRateGoal } from "@/components/DecisionEngine/LeadRateGoal";
import { Alert } from "@/components/ui/Alert";
import { SectionHeader } from "@/components/ui/SectionHeader";
import { apiFetch, type Client } from "@/lib/api";
export async function ClientGoalsSection({ client, definitionKey = "" }: { client: Client; definitionKey?: string }) {
  let rate: { target_lead_rate_pct: number | null } | null = null;
  try { rate = await apiFetch("/decisions/measurement-settings", { clientId: client.id }); } catch { /* Do not offer a blank target when its existing value is unknown. */ }
  return <div className="space-y-6">
    <section className="workspace-section"><SectionHeader title="Visit-based lead conversion target" description="Visits generating at least one lead, divided by all visits. Separate from lead-event counts and the measured baseline." /><div className="workspace-panel">{rate ? <LeadRateGoal key={`${client.id}-${rate.target_lead_rate_pct}`} clientId={client.id} slug={client.slug} initial={rate.target_lead_rate_pct} actual={null} expanded /> : <Alert variant="danger">The saved conversion-rate target could not be loaded.</Alert>}</div></section>
    <ClientAccountSection client={client} section="goals" />
    <section className="workspace-section"><SectionHeader title="Baseline & generated checkpoints" description="Calculate from saved lead definitions, review the projection, then lock explicitly. Existing baseline history is preserved." /><div className="workspace-panel"><BaselineBuilder key={`${client.id}-${definitionKey}`} clientId={client.id} currentGoal={client.monthly_lead_goal ?? null} /></div></section>
  </div>;
}
