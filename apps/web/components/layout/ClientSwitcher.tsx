"use client";

import { ChevronsUpDown } from "lucide-react";

import type { Client } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useWorkspaceParams } from "@/lib/workspace-params";

export function ClientSwitcher({
  clients,
  clientId,
  from,
  to,
}: {
  clients: Client[];
  clientId: string;
  from: string;
  to: string;
}) {
  const { pending, apply } = useWorkspaceParams({ clientId, from, to });
  const selected = clients.find((client) => client.id === clientId);

  return (
    <div className="relative">
      <ChevronsUpDown
        className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-tertiary)]"
        aria-hidden
      />
      <select
        aria-label="Client"
        className={cn(
          "w-full appearance-none rounded-lg border border-[var(--border-strong)] bg-[var(--surface)]",
          "py-2 pl-2.5 pr-8 text-left text-[0.8125rem] text-[var(--text-primary)]",
          "focus:border-[var(--border-focus)] focus:outline-none",
        )}
        value={clientId}
        disabled={pending || clients.length === 0}
        onChange={(event) => {
          const nextId = event.target.value;
          const next = clients.find((client) => client.id === nextId);
          apply({ clientId: nextId, clientSlug: next?.slug });
        }}
      >
        {clients.length === 0 ? <option value="">No clients</option> : null}
        {clients.map((client) => (
          <option key={client.id} value={client.id}>
            {client.client_name}
          </option>
        ))}
      </select>
      {selected?.domain ? (
        <p className="mt-1 truncate px-0.5 text-[0.6875rem] text-[var(--text-tertiary)]">
          {selected.domain}
        </p>
      ) : null}
    </div>
  );
}
