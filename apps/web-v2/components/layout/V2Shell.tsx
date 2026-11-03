"use client";

import { ChevronRight, MessageSquare } from "lucide-react";
import { useParams, usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { AskPanel } from "@/components/layout/AskPanel";
import { locate } from "@/components/layout/nav-config";
import { Sidebar } from "@/components/layout/Sidebar";
import type { Client } from "@/lib/api";

const ASK_KEY = "oiq-ask-open";

export function V2Shell({
  clients,
  userEmail,
  isAdmin = false,
  signOutAction,
  children,
}: {
  clients: Client[];
  userEmail?: string | null;
  isAdmin?: boolean;
  signOutAction: () => Promise<void>;
  children: React.ReactNode;
}) {
  const { clientSlug } = useParams<{ clientSlug?: string }>();
  const pathname = usePathname();
  const [ask, setAsk] = useState(false);
  useEffect(() => {
    try {
      setAsk(localStorage.getItem(ASK_KEY) === "1");
    } catch {
      /* closed until opened */
    }
  }, []);
  const setAskOpen = (open: boolean) => {
    setAsk(open);
    try {
      localStorage.setItem(ASK_KEY, open ? "1" : "0");
    } catch {
      /* kept for this visit only */
    }
  };

  const client = clients.find((c) => c.slug === clientSlug);
  const { group, page } = locate(pathname, clientSlug);

  return (
    <div className="flex min-h-screen">
      <Sidebar clients={clients} userEmail={userEmail} isAdmin={isAdmin} signOutAction={signOutAction} />
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-[var(--border)] bg-white px-6 py-2.5 text-sm">
          <nav aria-label="Breadcrumb" className="flex min-w-0 items-center gap-1.5 text-[var(--text-secondary)]">
            {client ? <span className="truncate">{client.client_name}</span> : null}
            {group ? <><ChevronRight size={14} aria-hidden /><span className="truncate">{group}</span></> : null}
            {page ? <><ChevronRight size={14} aria-hidden /><span className="truncate font-medium text-[var(--text-primary)]">{page}</span></> : null}
          </nav>
          <button
            type="button"
            aria-pressed={ask}
            onClick={() => setAskOpen(!ask)}
            className={`ml-auto flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold ${ask ? "border-[var(--brand-dark)] bg-[var(--brand-dark)] text-white" : "border-[#d6d9de] bg-white text-[var(--text-primary)] hover:bg-[var(--background)]"}`}
          >
            <MessageSquare size={14} aria-hidden /> Ask
          </button>
        </header>
        <main className="flex-1 p-8">{children}</main>
      </div>
      {ask ? <AskPanel context={[client?.client_name, page].filter(Boolean).join(" · ") || "Organic IQ"} onClose={() => setAskOpen(false)} /> : null}
    </div>
  );
}
