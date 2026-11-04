"use client";

import { useState, useTransition } from "react";

import { addFeedAction, removeFeedAction } from "@/app/(app)/[clientSlug]/settings/actions";
import type { ClientFeed } from "@/lib/feeds";

export function FeedSettings({
  clientId,
  slug,
  feeds,
}: {
  clientId: string;
  slug: string;
  feeds: ClientFeed[];
}) {
  const [url, setUrl] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function add() {
    setError(null);
    startTransition(async () => {
      const result = await addFeedAction(clientId, slug, url, label);
      if (result.ok) {
        setUrl("");
        setLabel("");
      } else {
        setError(result.error);
      }
    });
  }

  function remove(feedId: string) {
    setError(null);
    startTransition(async () => {
      const result = await removeFeedAction(clientId, slug, feedId);
      if (!result.ok) setError(result.error);
    });
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6">
      <h2 className="text-sm font-semibold">Feeds</h2>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        The blog or news feeds the content calendar checks for publish dates. Add more than one if
        the site has them.
      </p>

      <ul className="mt-4 divide-y divide-[var(--border)] text-sm">
        {feeds.length === 0 ? (
          <li className="py-2 text-[var(--text-tertiary)]">No feed added yet.</li>
        ) : (
          feeds.map((feed) => (
            <li key={feed.id} className="flex items-center justify-between gap-4 py-2">
              <span className="min-w-0">
                {feed.label ? <span className="font-medium">{feed.label} · </span> : null}
                <span className="break-all text-[var(--text-secondary)]">{feed.url}</span>
              </span>
              <button
                type="button"
                disabled={pending}
                onClick={() => remove(feed.id)}
                className="shrink-0 text-xs font-semibold text-red-700 hover:underline disabled:opacity-50"
              >
                Remove
              </button>
            </li>
          ))
        )}
      </ul>

      <form
        className="mt-4 grid gap-3 sm:grid-cols-[2fr_1fr_auto]"
        onSubmit={(event) => {
          event.preventDefault();
          add();
        }}
      >
        <input
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          placeholder="https://example.com/blog/feed.atom"
          aria-label="Feed address"
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
        />
        <input
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          placeholder="Label (optional)"
          aria-label="Feed label"
          className="rounded-lg border border-[var(--border)] px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={pending || !url.trim()}
          className="rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Add feed
        </button>
      </form>

      {error ? (
        <p role="alert" className="mt-3 rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      ) : null}
    </div>
  );
}
