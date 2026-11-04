"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { ThumbsDown, ThumbsUp } from "lucide-react";

import { askCopilotAction, rateCopilotMessageAction } from "@/app/(app)/copilot-actions";
import { Alert } from "@/components/ui/Alert";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";

type Turn =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "assistant";
      text: string;
      messageId: string;
      incomplete: boolean;
      rating: 1 | -1 | null;
    };

const STARTERS = [
  { label: "Summarize this month", prompt: "Summarize this client's month: the engine's constraint, the key numbers, and what we should do next." },
  { label: "Check the tool", prompt: "Check the tool for this client. Is every data source healthy and current, and is there anything stuck or stale I should fix?" },
  { label: "Why did traffic move?", prompt: "Did traffic or impressions change recently, and what does the data say about why? Check data health first." },
  { label: "Explain the plan", prompt: "Explain this month's Decision Engine plan in plain terms, slot by slot, and the status of each action." },
];

export function CopilotChat({ clientId, clientName }: { clientId: string; clientName: string }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns, pending]);

  function send(text: string) {
    const question = text.trim();
    if (!question || pending) return;
    setError(null);
    setDraft("");
    setTurns((t) => [...t, { id: `u${t.length}`, role: "user", text: question }]);
    startTransition(async () => {
      const result = await askCopilotAction(clientId, question, conversationId);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setConversationId(result.conversation_id);
      setTurns((t) => [
        ...t,
        {
          id: result.message_id,
          role: "assistant",
          text: result.reply,
          messageId: result.message_id,
          incomplete: result.incomplete,
          rating: null,
        },
      ]);
    });
  }

  function rate(messageId: string, value: 1 | -1) {
    const turn = turns.find((t) => t.role === "assistant" && t.messageId === messageId);
    if (!turn || turn.role !== "assistant") return;
    // A second click on the same thumb clears it.
    const next = turn.rating === value ? null : value;
    setTurns((all) =>
      all.map((t) => (t.role === "assistant" && t.messageId === messageId ? { ...t, rating: next } : t)),
    );
    void rateCopilotMessageAction(clientId, messageId, next ?? 0).then((res) => {
      if (!res.ok) {
        setTurns((all) =>
          all.map((t) =>
            t.role === "assistant" && t.messageId === messageId ? { ...t, rating: turn.rating } : t,
          ),
        );
        setError(res.error ?? "Could not save the rating.");
      }
    });
  }

  function reset() {
    setTurns([]);
    setConversationId(null);
    setError(null);
  }

  return (
    <div className="workspace-panel flex min-h-[28rem] flex-col gap-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[12px] text-[var(--text-tertiary)]">
          Answers use {clientName}&rsquo;s saved data only. Check figures before sending to a client.
        </p>
        {turns.length > 0 ? (
          <Button variant="ghost" size="sm" onClick={reset}>
            New chat
          </Button>
        ) : null}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto" aria-live="polite">
        {turns.length === 0 ? (
          <div className="grid gap-2 sm:grid-cols-2">
            {STARTERS.map((s) => (
              <button
                key={s.label}
                type="button"
                className="card px-3 py-3 text-left text-[13px] font-semibold text-[var(--text-primary)]"
                onClick={() => send(s.prompt)}
              >
                {s.label}
              </button>
            ))}
          </div>
        ) : null}

        {turns.map((turn) =>
          turn.role === "user" ? (
            <div key={turn.id} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-[var(--radius-lg)] bg-[var(--accent-soft)] px-3 py-2 text-[13px] text-[var(--text-primary)]">
                {turn.text}
              </p>
            </div>
          ) : (
            <div key={turn.id} className="max-w-[92%]">
              <p className="whitespace-pre-wrap rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-2 text-[13px] leading-relaxed text-[var(--text-primary)]">
                {turn.text}
              </p>
              {turn.incomplete ? (
                <p className="mt-1 text-[11.5px] text-[var(--text-tertiary)]">
                  Stopped before finishing. Ask a narrower question.
                </p>
              ) : null}
              <div className="mt-1 flex gap-1">
                <RateButton
                  label="Helpful"
                  active={turn.rating === 1}
                  onClick={() => rate(turn.messageId, 1)}
                >
                  <ThumbsUp size={14} />
                </RateButton>
                <RateButton
                  label="Not helpful"
                  active={turn.rating === -1}
                  onClick={() => rate(turn.messageId, -1)}
                >
                  <ThumbsDown size={14} />
                </RateButton>
              </div>
            </div>
          ),
        )}

        {pending ? (
          <p className="text-[12.5px] text-[var(--text-tertiary)]">Looking at the data…</p>
        ) : null}
        <div ref={bottomRef} />
      </div>

      {error ? <Alert variant="danger">{error}</Alert> : null}

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        <input
          className="field-control"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about this client…"
          maxLength={4000}
          aria-label="Ask the copilot"
          disabled={pending}
        />
        <Button type="submit" disabled={pending || !draft.trim()}>
          Ask
        </Button>
      </form>
    </div>
  );
}

function RateButton({
  label,
  active,
  onClick,
  children,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={active}
      title={label}
      onClick={onClick}
      className={cn(
        "rounded-[var(--radius-md)] p-1.5 text-[var(--text-tertiary)] hover:bg-[var(--surface-hover)]",
        active && "bg-[var(--accent-soft)] text-[var(--accent)]",
      )}
    >
      {children}
    </button>
  );
}
