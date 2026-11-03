"use client";

import { ChevronsUpDown, Plus } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { ClientFavicon } from "@/components/layout/ClientFavicon";
import type { Client } from "@/lib/api";

/** The client picker at the top of the sidebar: favicon, name and domain; opens a list of clients. */
export function ClientPicker({ clients }: { clients: Client[] }) {
  const pathname = usePathname();
  const first = pathname.split("/")[1];
  const current = clients.find((c) => c.slug === first);
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={box} className="relative mx-3 mt-3">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2.5 rounded-[10px] border border-[var(--brand-navy-line)] bg-[var(--brand-navy-deep)] px-2.5 py-2 text-left text-white hover:border-[var(--brand-teal-soft)]"
      >
        {current ? <ClientFavicon client={current} /> : <span className="h-7 w-7 rounded-[7px] bg-[var(--brand-navy-line)]" aria-hidden />}
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-medium leading-tight">{current?.client_name ?? "Choose a client"}</span>
          <span className="block truncate text-[0.7rem] text-[#9db3bd]">{current?.domain ?? `${clients.length} clients`}</span>
        </span>
        <ChevronsUpDown size={14} className="shrink-0 text-[#9db3bd]" aria-hidden />
      </button>
      {open ? (
        <div role="listbox" aria-label="Client" className="absolute inset-x-0 top-full z-40 mt-1 max-h-80 overflow-y-auto rounded-[10px] border border-[var(--border)] bg-white p-1 shadow-lg">
          {clients.map((c) => (
            <Link
              key={c.id}
              href={`/${c.slug}`}
              role="option"
              aria-selected={c.slug === current?.slug}
              onClick={() => setOpen(false)}
              className={`flex items-center gap-2.5 rounded-md px-2 py-1.5 text-sm text-[var(--text-primary)] hover:bg-[var(--background)] ${c.slug === current?.slug ? "bg-[var(--background)] font-semibold" : ""}`}
            >
              <ClientFavicon client={c} size={24} />
              <span className="min-w-0">
                <span className="block truncate">{c.client_name}</span>
                <span className="block truncate text-[0.7rem] font-normal text-[var(--text-secondary)]">{c.domain}</span>
              </span>
            </Link>
          ))}
          <Link href="/new-client" onClick={() => setOpen(false)} className="mt-1 flex items-center gap-2 border-t border-[var(--border)] px-2 pb-1.5 pt-2.5 text-sm font-semibold text-[var(--text-primary)] hover:text-[var(--brand-teal-hover)]">
            <Plus size={14} aria-hidden /> Add client
          </Link>
        </div>
      ) : null}
    </div>
  );
}
