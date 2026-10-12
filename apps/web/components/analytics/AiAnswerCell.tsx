"use client";

import { useState } from "react";

type Answer = {
  available: boolean;
  reason?: string;
  date?: string;
  text?: string | null;
  sources?: { url: string; position: number | null }[];
  brands?: { name: string; position: number | null }[];
};

/**
 * What the model actually said, fetched when somebody asks.
 *
 * The synced rankings carry a position and a count and no URL — "cited at 2
 * of 9" with nothing to open. The answer is one API call per prompt per
 * day, so it is paid for by the person who opens it rather than by a sync
 * that would make a thousand calls a day for something almost nobody reads.
 */
export function AiAnswerCell({
  clientId,
  promptId,
  cited,
}: {
  clientId: string;
  promptId: string;
  cited: boolean | null;
}) {
  const [open, setOpen] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    if (answer || loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `/api/proxy/ai-answer?clientId=${encodeURIComponent(clientId)}` +
          `&promptId=${encodeURIComponent(promptId)}`,
      );
      if (!res.ok) throw new Error("Could not load the answer");
      setAnswer((await res.json()) as Answer);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load the answer");
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={toggle}
        className="text-[12px] font-semibold text-[var(--brand-teal-hover)] underline"
      >
        {open ? "Hide" : cited ? "Sources" : "What it said"}
      </button>

      {open ? (
        <div className="mt-2 max-w-[42rem] rounded-[8px] border border-[var(--border)] bg-[var(--surface-muted)] p-3 text-[12px]">
          {loading ? <p>Asking SE Ranking…</p> : null}
          {error ? <p className="text-[#B4441C]">{error}</p> : null}
          {answer && !answer.available ? (
            <p className="text-[var(--text-secondary)]">{answer.reason}</p>
          ) : null}
          {answer?.available ? (
            <div className="space-y-2">
              <div>
                <p className="font-semibold">Cited</p>
                {answer.sources?.length ? (
                  <ol className="mt-0.5 space-y-0.5">
                    {answer.sources.map((source) => (
                      <li key={source.url}>
                        <span className="mr-1.5 text-[var(--text-tertiary)]">
                          {source.position ?? "–"}.
                        </span>
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noreferrer"
                          className="font-[family-name:var(--font-mono)] text-[11.5px] break-all text-[var(--brand-teal-hover)]"
                        >
                          {source.url}
                        </a>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="text-[var(--text-secondary)]">
                    The answer cited nothing.
                  </p>
                )}
              </div>

              {/* Who the model named alongside: the competitive read that
                  a position and a count cannot give. */}
              {answer.brands?.length ? (
                <div>
                  <p className="font-semibold">Named in the answer</p>
                  <p className="mt-0.5 text-[var(--text-secondary)]">
                    {answer.brands
                      .map((brand) => `${brand.position ?? "–"}. ${brand.name}`)
                      .join("  ·  ")}
                  </p>
                </div>
              ) : null}

              {answer.text ? (
                <details>
                  <summary className="cursor-pointer font-semibold">
                    The answer itself
                  </summary>
                  <p className="mt-1 whitespace-pre-wrap text-[var(--text-secondary)]">
                    {answer.text}
                  </p>
                </details>
              ) : null}

              {answer.date ? (
                <p className="text-[11px] text-[var(--text-tertiary)]">
                  As answered on {answer.date}.
                </p>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}
    </>
  );
}
