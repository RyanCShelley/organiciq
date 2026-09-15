"use client";

import { ShieldCheck, UserMinus, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  assignClientAccessAction,
  removeClientAccessAction,
  type ClientTeamMember,
} from "@/app/(app)/team-actions";
import { Alert } from "@/components/ui/Alert";
import { Select } from "@/components/ui/Input";
import type { User } from "@/lib/api";

export function ClientTeamPanel({
  clientId,
  clientName,
  team,
  users,
  canManage,
}: {
  clientId: string;
  clientName: string;
  team: ClientTeamMember[];
  users: User[];
  canManage: boolean;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selected, setSelected] = useState("");

  // Admins already see every client, so offering to "add" them is noise.
  const assignable = users.filter(
    (user) =>
      user.role !== "sma_admin" && !team.some((member) => member.user_id === user.id),
  );

  function run(action: () => Promise<{ ok: boolean; error?: string }>, done: string) {
    setError(null);
    setMessage(null);
    startTransition(async () => {
      const result = await action();
      if (!result.ok) {
        setError(result.error ?? "Something went wrong");
        return;
      }
      setMessage(done);
      setSelected("");
      router.refresh();
    });
  }

  if (!canManage) {
    return (
      <Alert variant="info">
        Only an SMA admin can manage who sees this client.
      </Alert>
    );
  }

  return (
    <div className="space-y-3">
      {error ? <Alert variant="danger">{error}</Alert> : null}
      {message ? <Alert variant="success">{message}</Alert> : null}

      <ul className="divide-y divide-[var(--border)] rounded-[var(--radius-md)] border border-[var(--border)]">
        {team.map((member) => (
          <li
            key={member.user_id}
            className="flex flex-wrap items-center justify-between gap-3 px-3 py-2.5"
          >
            <div className="min-w-0">
              <p className="truncate text-[13.5px] font-medium text-[var(--text-primary)]">
                {member.name || member.email}
              </p>
              <p className="truncate text-xs text-[var(--text-tertiary)]">{member.email}</p>
            </div>
            {member.via_admin ? (
              <span
                className="badge badge-accent gap-1"
                title="Admins see every client; access is not per-client"
              >
                <ShieldCheck className="h-3 w-3" aria-hidden />
                Admin — all clients
              </span>
            ) : (
              <button
                type="button"
                className="btn btn-sm btn-ghost gap-1.5 text-[var(--danger)] hover:bg-[var(--danger-soft)] hover:text-[var(--danger)]"
                disabled={pending}
                onClick={() =>
                  run(
                    () => removeClientAccessAction(clientId, member.user_id),
                    `Removed ${member.email} from ${clientName}.`,
                  )
                }
              >
                <UserMinus className="h-3.5 w-3.5" aria-hidden />
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>

      {assignable.length > 0 ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="field-label flex-1 min-w-[16rem]">
            Give a team member access
            <Select value={selected} onChange={(event) => setSelected(event.target.value)}>
              <option value="">Select a person…</option>
              {assignable.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name ? `${user.name} — ${user.email}` : user.email}
                </option>
              ))}
            </Select>
          </label>
          <button
            type="button"
            className="btn btn-primary gap-2"
            disabled={pending || !selected}
            onClick={() =>
              run(
                () => assignClientAccessAction(clientId, selected),
                `Added access to ${clientName}.`,
              )
            }
          >
            <UserPlus className="h-3.5 w-3.5" aria-hidden />
            {pending ? "Saving…" : "Add"}
          </button>
        </div>
      ) : (
        <p className="text-xs text-[var(--text-tertiary)]">
          {users.length <= team.length
            ? "Everyone who has signed in already has access."
            : "No one left to add."}{" "}
          People appear here after their first sign-in.
        </p>
      )}
    </div>
  );
}
