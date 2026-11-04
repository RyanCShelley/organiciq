export type ClientFeed = { id: string; url: string; label: string | null };

export type FeedActionResult = { ok: true } | { ok: false; error: string };
