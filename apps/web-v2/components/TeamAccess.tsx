"use client";

import { useState, useTransition } from "react";

import {
  assignUserAction,
  unassignUserAction,
} from "@/app/(app)/[clientSlug]/settings/client-actions";
import { Card, inputClass } from "@/components/ui/form";

export type TeamMember = {
  user_id: string;
  email: string;
  name: string | null;
  role: string;
  is_active: boolean;
  via_admin: boolean;
};
export type StaffUser = { id: string; email: string; name: string | null; role: string; is_active: boolean };

export function TeamAccess({
  clientId,
  slug,
  team,
  users,
}: {
  clientId: string;
  slug: string;
  team: TeamMember[];
  users: StaffUser[];
}) {
  const [pick, setPick] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const onTeam = new Set(team.map((m) => m.user_id));
  const addable = users.filter((u) => u.is_active && !onTeam.has(u.id));

  function run(task: () => Promise<{ ok: true } | { ok: false; error: string }>) {
    setError(null);
    startTransition(async () => {
      const result = await task();
      if (!result.ok) setError(result.error);
      else setPick("");
    });
  }

  return (
    <Card title="Who can see this client">
      <ul className="divide-y divide-[var(--border)] text-sm">
        {team.map((member) => (
          <li key={member.user_id} className="flex items-center justify-between gap-4 py-2">
            <span>
              <span className="font-medium">{member.name || member.email}</span>
              {member.name ? <span className="text-[var(--text-secondary)]"> · {member.email}</span> : null}
            </span>
            {member.via_admin ? (
              <span className="text-xs text-[var(--text-tertiary)]">Admin: sees every client</span>
            ) : (
              <button
                type="button"
                disabled={pending}
                onClick={() => run(() => unassignUserAction(clientId, slug, member.user_id))}
                className="text-xs font-semibold text-red-700 hover:underline disabled:opacity-50"
              >
                Remove
              </button>
            )}
          </li>
        ))}
      </ul>

      <div className="mt-4 flex gap-3">
        <select
          value={pick}
          onChange={(e) => setPick(e.target.value)}
          aria-label="Person to add"
          className={inputClass}
        >
          <option value="">
            {addable.length ? "Add a person" : "Everyone who has signed in already has access"}
          </option>
          {addable.map((u) => (
            <option key={u.id} value={u.id}>
              {u.name ? `${u.name} · ${u.email}` : u.email}
            </option>
          ))}
        </select>
        <button
          type="button"
          disabled={pending || !pick}
          onClick={() => run(() => assignUserAction(clientId, slug, pick))}
          className="shrink-0 rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Give access
        </button>
      </div>
      <p className="mt-2 text-xs text-[var(--text-secondary)]">
        People appear here after they have signed in once.
      </p>
      {error ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}
    </Card>
  );
}
