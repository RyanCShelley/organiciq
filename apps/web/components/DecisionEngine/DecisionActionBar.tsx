"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  createTeamworkTaskStubAction,
  updateDecisionStatusAction,
} from "@/app/(app)/actions";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { StoredDecision } from "@/lib/decision-engine";

const LOCKED = new Set(["task_created", "completed", "validated"]);

export function DecisionActionBar({
  clientId,
  from,
  to,
  ruleKey,
  decision,
}: {
  clientId: string;
  from: string;
  to: string;
  ruleKey: string;
  decision?: StoredDecision | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [showDismiss, setShowDismiss] = useState(false);
  const [dismissalReason, setDismissalReason] = useState("");

  const status = decision?.status ?? null;
  const isAccepted = status === "accepted";
  const isDismissed = status === "dismissed";
  const isLocked = status != null && LOCKED.has(status);

  function runStatus(nextStatus: string, reason?: string) {
    setError(null);
    setMessage(null);
    const formData = new FormData();
    formData.set("clientId", clientId);
    formData.set("from", from);
    formData.set("to", to);
    formData.set("ruleKey", ruleKey);
    formData.set("decisionId", decision?.id ?? "");
    formData.set("status", nextStatus);
    if (reason) formData.set("dismissal_reason", reason);

    startTransition(async () => {
      const result = await updateDecisionStatusAction(formData);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      const feedback: Record<string, string> = {
        dismissed: "Decision dismissed.",
        accepted: "Decision accepted.",
        reviewed: "Decision marked reviewed.",
        new: "Selection cleared.",
      };
      setMessage(feedback[nextStatus] ?? "Decision updated.");
      setShowDismiss(false);
      setDismissalReason("");
      router.refresh();
    });
  }

  function runTaskStub() {
    setError(null);
    setMessage(null);
    const formData = new FormData();
    formData.set("clientId", clientId);
    formData.set("from", from);
    formData.set("to", to);
    formData.set("ruleKey", ruleKey);
    formData.set("decisionId", decision?.id ?? "");

    startTransition(async () => {
      const result = await createTeamworkTaskStubAction(formData);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setMessage("Marked task created (Teamwork API not connected yet).");
      router.refresh();
    });
  }

  return (
    <div className="mt-4 space-y-2 border-t border-[var(--border)] pt-3">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}
      {decision?.dismissal_reason ? (
        <p className="text-xs text-[var(--text-secondary)]">
          Dismissed:{" "}
          <span className="font-medium text-[var(--text-primary)]">
            {decision.dismissal_reason}
          </span>
        </p>
      ) : null}

      {isLocked ? (
        <p className="text-xs text-[var(--text-tertiary)]">
          This decision is {status?.replaceAll("_", " ")}. Re-evaluate the period to reopen
          workflow for a new window.
        </p>
      ) : null}

      {isDismissed ? (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => runStatus("new")}
          >
            Undo dismiss
          </Button>
        </div>
      ) : null}

      {isAccepted && !isLocked ? (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => runStatus("new")}
          >
            Deselect
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={() => setShowDismiss((open) => !open)}
          >
            Dismiss instead
          </Button>
          <Button
            type="button"
            variant="tertiary"
            size="sm"
            disabled={pending}
            onClick={runTaskStub}
          >
            Mark task created
          </Button>
        </div>
      ) : null}

      {!isAccepted && !isDismissed && !isLocked ? (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={pending}
            onClick={() => runStatus("reviewed")}
          >
            Mark reviewed
          </Button>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={pending}
            onClick={() => runStatus("accepted")}
          >
            Accept
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={() => setShowDismiss((open) => !open)}
          >
            Dismiss
          </Button>
          <Button
            type="button"
            variant="tertiary"
            size="sm"
            disabled={pending}
            onClick={runTaskStub}
          >
            Mark task created
          </Button>
        </div>
      ) : null}

      {showDismiss && !isLocked && !isDismissed ? (
        <div className="flex flex-wrap items-end gap-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-muted)] p-3">
          <label className="field-label min-w-[220px] flex-1">
            Dismissal reason
            <Input
              value={dismissalReason}
              onChange={(event) => setDismissalReason(event.target.value)}
              placeholder="Why skip this action?"
              required
            />
          </label>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={pending || !dismissalReason.trim()}
            onClick={() => runStatus("dismissed", dismissalReason.trim())}
          >
            Confirm dismiss
          </Button>
        </div>
      ) : null}

      {!isLocked && !isDismissed ? (
        <p className="text-xs text-[var(--text-tertiary)]">
          Accept counts toward Selected on the plan. Deselect clears that without dismissing.
        </p>
      ) : null}
    </div>
  );
}
