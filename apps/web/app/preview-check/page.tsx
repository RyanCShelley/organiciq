import { ActionLedger } from "@/components/DecisionEngine/ActionLedger";
import { ConstraintBand } from "@/components/DecisionEngine/ConstraintBand";
import {
  normalizeDiagnoseResponse,
  type DiagnoseResponse,
  type StoredDecision,
} from "@/lib/decision-engine";
import payload from "../../.sma-served-payload.json";

export default function Preview() {
  const data = normalizeDiagnoseResponse(payload as unknown as DiagnoseResponse);
  return (
    <section className="mx-auto max-w-[1100px] space-y-8 p-8">
      {data.constraint ? <ConstraintBand constraint={data.constraint} /> : <p>NO CONSTRAINT</p>}
      <ActionLedger
        actions={data.growth_actions ?? []}
        blocking={data.blocking_findings ?? []}
        allowance={5}
        planLabel="Lead"
        clientId="preview"
        from="2026-09-09"
        to="2026-10-08"
        decisionsByRule={new Map<string, StoredDecision>()}
      />
    </section>
  );
}
