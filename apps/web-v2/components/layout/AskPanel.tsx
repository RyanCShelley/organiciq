"use client";

import { Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";

import { askInfoAction } from "@/app/(app)/[clientSlug]/bi/actions";
import { AskTheData } from "@/components/bi/AskTheData";
import { Spinner } from "@/components/ui/Spinner";
import type { AskInfo } from "@/lib/bi";

/**
 * The chat on the right, on every page. It sends what is on screen with each question, so an answer starts from the page the person
 * is looking at and queries the client's data only for what the page does not show.
 */
export function AskPanel({ clientId, page, examples, onClose }: { clientId: string | null; page: string; examples?: string[]; onClose: () => void }) {
  const [info, setInfo] = useState<AskInfo | null | undefined>(undefined);
  useEffect(() => {
    setInfo(undefined);
    // A slow answer for the client just left must not land on the one chosen now.
    let live = true;
    if (clientId) void askInfoAction(clientId).then((r) => live && setInfo(r));
    return () => {
      live = false;
    };
  }, [clientId]);

  // Read when a question is sent, so it is the page as it is then, not as it was when the panel opened.
  const getPage = () => {
    const text = (document.querySelector("main") as HTMLElement | null)?.innerText.replace(/\s+/g, " ").trim().slice(0, 12000) ?? "";
    return text ? { name: page.slice(0, 80), text } : null;
  };

  return (
    <aside aria-label="Ask Organic IQ" className="fixed right-0 top-0 z-30 flex h-screen w-[360px] max-w-full shrink-0 flex-col border-l border-[var(--border)] bg-white shadow-xl xl:sticky xl:z-auto xl:shadow-none">
      <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
        <Sparkles size={16} className="text-[var(--brand-teal)]" aria-hidden />
        <h2 className="text-base font-bold">Ask Organic IQ</h2>
        <button type="button" onClick={onClose} aria-label="Close Ask" className="ml-auto rounded-md p-1.5 text-[var(--text-secondary)] hover:bg-[var(--background)]">
          <X size={16} aria-hidden />
        </button>
      </div>
      <p className="mx-4 mt-3 w-fit max-w-full truncate rounded-full bg-[var(--brand-teal-soft)] px-2.5 py-0.5 text-[0.7rem] font-medium text-[#006b63]" title={page}>{page}</p>
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
        {!clientId ? (
          <p className="text-sm text-[var(--text-secondary)]">Choose a client to ask about its data.</p>
        ) : info === undefined ? (
          <p className="text-sm text-[var(--text-secondary)]"><Spinner />Loading…</p>
        ) : (
          <AskTheData key={clientId} clientId={clientId} info={info} embedded getPage={getPage} examples={examples} />
        )}
      </div>
    </aside>
  );
}
