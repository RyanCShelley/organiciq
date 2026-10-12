"use client";

import { Check, ChevronsUpDown, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { Client } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useWorkspaceParams } from "@/lib/workspace-params";

/** Two letters from the name, for a client that has no logo stored. */
function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[1][0]).toUpperCase();
}

/**
 * A stable colour per client, so the chip is recognisable before it is read.
 *
 * Derived from the slug rather than stored, so a new client has one without
 * anybody choosing it, and it never changes under a client that is renamed.
 */
function chipColor(seed: string): string {
  const palette = [
    "#2C4A86", "#15784F", "#8E3414", "#6B3A06",
    "#4A2C86", "#0F6B74", "#8A4B08", "#3E4954",
  ];
  let hash = 0;
  for (const char of seed) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return palette[hash % palette.length];
}

/**
 * The client picker.
 *
 * A native `<select>` renders as an operating-system menu: no search, no
 * structure, and at two dozen clients it is a scrolling list of names in
 * whatever font the OS picked. This is a button and a popover, which can
 * hold a search box and show the domain — the thing that tells two
 * similarly named clients apart.
 */
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

  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = needle
      ? clients.filter(
          (client) =>
            client.client_name.toLowerCase().includes(needle) ||
            (client.domain ?? "").toLowerCase().includes(needle),
        )
      : clients;
    return [...rows].sort((a, b) => a.client_name.localeCompare(b.client_name));
  }, [clients, query]);

  // Clicking away and Escape both close it; without the first, the popover
  // outlives the thought that opened it.
  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      // Typing is how you pick one of twenty-four, so the caret starts there.
      requestAnimationFrame(() => searchRef.current?.focus());
    }
  }, [open]);

  function choose(client: Client) {
    setOpen(false);
    if (client.id === clientId) return;
    apply({ clientId: client.id, clientSlug: client.slug });
  }

  function onKeyDown(event: React.KeyboardEvent) {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setActive((current) => {
        const next = current + (event.key === "ArrowDown" ? 1 : -1);
        return Math.max(0, Math.min(matches.length - 1, next));
      });
      return;
    }
    if (event.key === "Enter" && matches[active]) {
      event.preventDefault();
      choose(matches[active]);
    }
  }

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Client"
        disabled={pending || clients.length === 0}
        onClick={() => setOpen((value) => !value)}
        className={cn(
          "flex w-full items-center gap-2 rounded-[10px] px-2 py-2 text-left disabled:opacity-60",
          dark
            ? "border border-[var(--sidebar-border-strong)] bg-[var(--sidebar-field)] text-[var(--sidebar-fg)]"
            : "border border-[var(--border-strong)] bg-[var(--surface)] text-[var(--text-primary)]",
        )}
      >
        {selected ? (
          <span
            aria-hidden
            className="flex h-7 w-7 flex-none items-center justify-center rounded-[7px] text-[11px] font-bold text-white"
            style={{ background: chipColor(selected.slug) }}
          >
            {initials(selected.client_name)}
          </span>
        ) : null}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-semibold">
            {selected?.client_name ?? "No clients"}
          </span>
          {/* The domain is what tells two similarly named clients apart. */}
          {selected?.domain ? (
            <span
              className={cn(
                "block truncate text-[11px] font-normal",
                dark ? "text-[var(--sidebar-fg-muted)]" : "text-[var(--text-tertiary)]",
              )}
            >
              {selected.domain}
            </span>
          ) : null}
        </span>
        <ChevronsUpDown
          className={cn(
            "h-3.5 w-3.5 flex-none",
            dark ? "text-[var(--sidebar-fg-muted)]" : "text-[var(--text-tertiary)]",
          )}
          aria-hidden
        />
      </button>

      {open ? (
        <div
          role="listbox"
          aria-label="Clients"
          onKeyDown={onKeyDown}
          className="absolute left-0 right-0 z-50 mt-1 overflow-hidden rounded-[10px] border border-[var(--border-strong)] bg-[var(--surface)] shadow-lg"
        >
          <div className="flex items-center gap-2 border-b border-[var(--border)] px-2.5 py-2">
            <Search className="h-3.5 w-3.5 flex-none text-[var(--text-tertiary)]" aria-hidden />
            <input
              ref={searchRef}
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setActive(0);
              }}
              onKeyDown={onKeyDown}
              placeholder="Search clients…"
              aria-label="Search clients"
              className="w-full bg-transparent text-[13px] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] focus:outline-none"
            />
          </div>

          <ul className="max-h-[22rem] overflow-y-auto py-1">
            {matches.length === 0 ? (
              <li className="px-3 py-3 text-[12.5px] text-[var(--text-secondary)]">
                Nothing matches “{query}”.
              </li>
            ) : null}
            {matches.map((client, index) => {
              const current = client.id === clientId;
              return (
                <li key={client.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={current}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => choose(client)}
                    className={cn(
                      "flex w-full items-center gap-2 px-2.5 py-1.5 text-left",
                      index === active && "bg-[var(--surface-muted)]",
                    )}
                  >
                    <span
                      aria-hidden
                      className="flex h-6 w-6 flex-none items-center justify-center rounded-[6px] text-[10px] font-bold text-white"
                      style={{ background: chipColor(client.slug) }}
                    >
                      {initials(client.client_name)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] font-medium text-[var(--text-primary)]">
                        {client.client_name}
                      </span>
                      {client.domain ? (
                        <span className="block truncate text-[11px] text-[var(--text-tertiary)]">
                          {client.domain}
                        </span>
                      ) : null}
                    </span>
                    {current ? (
                      <Check className="h-3.5 w-3.5 flex-none text-[var(--brand-teal-hover)]" aria-hidden />
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
