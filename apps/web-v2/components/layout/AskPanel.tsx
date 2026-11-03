"use client";

import { Sparkles, X } from "lucide-react";

/** The chat on the right, which will answer from the page it sits on. This is the panel; the answers come next. */
export function AskPanel({ context, onClose }: { context: string; onClose: () => void }) {
  return (
    <aside aria-label="Ask Organic IQ" className="sticky top-0 flex h-screen w-[340px] shrink-0 flex-col border-l border-[var(--border)] bg-white">
      <div className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3">
        <Sparkles size={16} className="text-[var(--brand-teal)]" aria-hidden />
        <h2 className="text-base font-bold">Ask Organic IQ</h2>
        <button type="button" onClick={onClose} aria-label="Close Ask" className="ml-auto rounded-md p-1.5 text-[var(--text-secondary)] hover:bg-[var(--background)]">
          <X size={16} aria-hidden />
        </button>
      </div>
      <p className="mx-4 mt-3 w-fit max-w-full truncate rounded-full bg-[var(--brand-teal-soft)] px-2.5 py-0.5 text-[0.7rem] font-medium text-[#006b63]" title={context}>{context}</p>
      <div className="flex-1 space-y-2 px-4 py-4 text-sm text-[var(--text-secondary)]">
        <p className="font-semibold text-[var(--text-primary)]">Ask is coming next.</p>
        <p>It will read the page you are on and the client&apos;s data behind it, and answer in plain words with where each number came from.</p>
      </div>
    </aside>
  );
}
