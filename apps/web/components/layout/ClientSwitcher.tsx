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
  tone = "light",
}: {
  clients: Client[];
  clientId: string;
  from: string;
  to: string;
  tone?: "light" | "dark";
}) {
  const { pending, apply } = useWorkspaceParams({ clientId, from, to });
  const selected = clients.find((client) => client.id === clientId);
  const dark = tone === "dark";

  return (
    <div>
      {/* The chevron centres on the select only — the domain line sits outside
          this box, or `top-1/2` would measure against both. */}
      <div className="relative flex">
        <ChevronsUpDown
          className={cn(
            "pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2",
            dark
              ? "text-[var(--sidebar-fg-muted)]"
              : "text-[var(--text-tertiary)]",
          )}
          aria-hidden
        />
        <select
          aria-label="Client"
          className={cn(
            "w-full appearance-none rounded-[10px] py-2 pl-2.5 pr-8 text-left text-[13.5px] font-semibold focus:outline-none",
            dark
              ? "border border-[var(--sidebar-border-strong)] bg-[var(--sidebar-field)] text-[var(--sidebar-fg)] focus:border-[var(--brand-teal)]"
              : "border border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text-primary)] focus:border-[var(--border-focus)]",
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
      </div>
      {selected?.domain ? (
        <p
          className={cn(
            "mt-1 truncate px-0.5 text-[11px]",
            dark
              ? "text-[var(--sidebar-fg-muted)]"
              : "text-[var(--text-tertiary)]",
          )}
        >
          {selected.domain}
        </p>
      ) : null}
    </div>
  );
}
