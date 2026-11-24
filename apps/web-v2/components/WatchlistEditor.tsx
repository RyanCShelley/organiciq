"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import {
  addKeywordAction,
  bulkAddKeywordsAction,
  createBucketAction,
  deleteBucketAction,
  deleteKeywordAction,
  fetchWatchlistSuggestionsAction,
  updateBucketAction,
  updateKeywordAction,
} from "@/app/(app)/[clientSlug]/watchlist/actions";
import { WatchlistImport } from "@/components/WatchlistImport";
import { Field, inputClass } from "@/components/ui/form";
import type {
  ImportReport,
  Watchlist,
  WatchlistBucket,
  WatchlistKeyword,
  WatchlistKeywordCreateInput,
  WatchlistKeywordUpdateInput,
  WatchlistSuggestion,
  WatchlistSuggestionsResponse,
} from "@/lib/watchlist";

type WatchlistEditorProps = {
  clientId: string;
  clientSlug: string;
  clientName: string;
  initialWatchlist: Watchlist;
  initialSuggestions: WatchlistSuggestionsResponse | null;
};

const NEW_BUCKET_VALUE = "__new__";

const SIGNAL_LABELS: Record<string, { label: string; cls: string }> = {
  high_impressions: { label: "High impressions", cls: "bg-[#eef0f1] text-[#223540]" },
  rising: { label: "Rising", cls: "bg-[#e6f7f5] text-[#00665f]" },
  new: { label: "New", cls: "bg-amber-50 text-amber-800" },
  relevant: { label: "Relevant", cls: "bg-sky-50 text-sky-800" },
};

function normalizeKey(value: string): string {
  return value.trim().toLowerCase().replace(/\s+/g, " ");
}

function shortPath(url: string): string {
  return url.replace(/^https?:\/\/[^/]+/, "") || "/";
}

export function WatchlistEditor({
  clientId,
  clientSlug,
  clientName,
  initialWatchlist,
  initialSuggestions,
}: WatchlistEditorProps) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();

  const buckets = initialWatchlist.buckets;
  const [pendingBuckets, setPendingBuckets] = useState<
    { id: string; name: string; sort_order: number }[]
  >([]);

  useEffect(() => {
    setPendingBuckets((prev) => {
      if (prev.length === 0) return prev;
      const propIds = new Set(buckets.map((b) => b.id));
      const remaining = prev.filter((p) => !propIds.has(p.id));
      return remaining.length === prev.length ? prev : remaining;
    });
  }, [buckets]);

  const availableBuckets = useMemo(() => {
    const propIds = new Set(buckets.map((b) => b.id));
    const extras = pendingBuckets
      .filter((p) => !propIds.has(p.id))
      .map((p) => ({ ...p, keywords: [] as WatchlistKeyword[] }));
    return [...buckets, ...extras];
  }, [buckets, pendingBuckets]);

  function rememberPendingBucket(bucket: { id: string; name: string; sort_order?: number }) {
    setPendingBuckets((prev) => {
      if (buckets.some((b) => b.id === bucket.id) || prev.some((b) => b.id === bucket.id)) {
        return prev;
      }
      const maxOrder = [...buckets, ...prev].reduce(
        (max, b) => Math.max(max, b.sort_order),
        -1,
      );
      return [
        ...prev,
        {
          id: bucket.id,
          name: bucket.name,
          sort_order: bucket.sort_order ?? maxOrder + 1,
        },
      ];
    });
  }

  const suggestionsReqIdRef = useRef(0);

  // Filter & banner state
  const [searchQuery, setSearchQuery] = useState("");
  const [bucketFilter, setBucketFilter] = useState<string>("all");
  const [banner, setBanner] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  // 1-line inline quick-add bar
  const [quickKeyword, setQuickKeyword] = useState("");
  const [quickBucketChoice, setQuickBucketChoice] = useState<string>(buckets[0]?.id ?? "");
  const [quickNewBucketName, setQuickNewBucketName] = useState("");
  const [quickError, setQuickError] = useState<string | null>(null);

  // Embedded CSV import drawer
  const [importOpen, setImportOpen] = useState(false);

  // New bucket inline bar
  const [newBucketOpen, setNewBucketOpen] = useState(false);
  const [newBucketName, setNewBucketName] = useState("");
  const [newBucketError, setNewBucketError] = useState<string | null>(null);

  // Bucket rename / delete state
  const [renamingBucketId, setRenamingBucketId] = useState<string | null>(null);
  const [renameBucketValue, setRenameBucketValue] = useState("");
  const [renameBucketError, setRenameBucketError] = useState<string | null>(null);
  const [confirmDeleteBucketId, setConfirmDeleteBucketId] = useState<string | null>(null);

  // Keyword inline delete confirmation
  const [confirmDeleteKeywordId, setConfirmDeleteKeywordId] = useState<string | null>(null);

  // Keyword Add/Edit slide-over drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editingKeyword, setEditingKeyword] = useState<WatchlistKeyword | null>(null);
  const [editingOriginBucketId, setEditingOriginBucketId] = useState<string | null>(null);
  const [kwInput, setKwInput] = useState("");
  const [kwBucketChoice, setKwBucketChoice] = useState<string>("");
  const [kwNewBucketName, setKwNewBucketName] = useState("");
  const [showOptionalMetadata, setShowOptionalMetadata] = useState(false);
  const [kwVolume, setKwVolume] = useState("");
  const [kwDifficulty, setKwDifficulty] = useState("");
  const [kwIntent, setKwIntent] = useState("");
  const [kwPrompt, setKwPrompt] = useState("");
  const [kwNotes, setKwNotes] = useState("");
  const [drawerError, setDrawerError] = useState<string | null>(null);

  // GSC Suggestions slide-over drawer
  const [suggestionsOpen, setSuggestionsOpen] = useState(false);
  const [suggestionsData, setSuggestionsData] = useState<WatchlistSuggestionsResponse | null>(
    initialSuggestions,
  );
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [suggestionsError, setSuggestionsError] = useState<string | null>(null);
  const [suggSearchInput, setSuggSearchInput] = useState("");
  const [suggActiveSearch, setSuggActiveSearch] = useState("");
  const [suggDays, setSuggDays] = useState<28 | 90>(90);
  const [suggBucketChoice, setSuggBucketChoice] = useState<string>(
    buckets[0]?.id ?? NEW_BUCKET_VALUE,
  );
  const [suggNewBucketName, setSuggNewBucketName] = useState("General");
  const [selectedSuggestionKeys, setSelectedSuggestionKeys] = useState<Set<string>>(new Set());
  const [recentlyAddedKeys, setRecentlyAddedKeys] = useState<Set<string>>(new Set());
  const [addingSuggestionKey, setAddingSuggestionKey] = useState<string | null>(null);

  useEffect(() => {
    if (!suggActiveSearch && suggDays === 90) {
      setSuggestionsData(initialSuggestions);
    }
  }, [initialSuggestions, suggActiveSearch, suggDays]);

  const existingKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const b of buckets) {
      for (const kw of b.keywords) {
        keys.add(normalizeKey(kw.keyword));
      }
    }
    return keys;
  }, [buckets]);

  const filteredBuckets = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    return buckets
      .filter((b) => bucketFilter === "all" || b.id === bucketFilter)
      .map((b) => {
        if (!q) return b;
        const bucketMatches = b.name.toLowerCase().includes(q);
        const matchingKeywords = bucketMatches
          ? b.keywords
          : b.keywords.filter((k) =>
              [k.keyword, k.intent ?? "", k.paired_ai_prompt ?? "", k.notes ?? ""]
                .join(" ")
                .toLowerCase()
                .includes(q),
            );
        return { ...b, keywords: matchingKeywords };
      })
      .filter((b) => !q || b.keywords.length > 0 || b.name.toLowerCase().includes(q));
  }, [buckets, bucketFilter, searchQuery]);

  const visibleSuggestions = useMemo(() => {
    if (!suggestionsData) return [];
    return suggestionsData.suggestions.filter((s) => !existingKeys.has(normalizeKey(s.key)));
  }, [suggestionsData, existingKeys]);

  const effectiveQuickBucket =
    quickBucketChoice === NEW_BUCKET_VALUE
      ? NEW_BUCKET_VALUE
      : availableBuckets.some((b) => b.id === quickBucketChoice)
        ? quickBucketChoice
        : (availableBuckets[0]?.id ?? "");

  function handleQuickAdd(event: React.FormEvent) {
    event.preventDefault();
    setQuickError(null);
    const trimmedKw = quickKeyword.trim().replace(/\s+/g, " ");
    if (!trimmedKw) {
      setQuickError("Enter a keyword to add.");
      return;
    }

    const useNewBucket = effectiveQuickBucket === NEW_BUCKET_VALUE;
    const trimmedNewBucket = quickNewBucketName.trim().replace(/\s+/g, " ");
    if (useNewBucket && !trimmedNewBucket) {
      setQuickError("Enter a bucket name.");
      return;
    }

    const payload: WatchlistKeywordCreateInput = {
      keyword: trimmedKw,
      ...(useNewBucket
        ? { bucket_name: trimmedNewBucket }
        : effectiveQuickBucket
          ? { bucket_id: effectiveQuickBucket }
          : {}),
    };

    startTransition(async () => {
      const res = await addKeywordAction(clientId, clientSlug, payload);
      if (!res.ok) {
        setQuickError(res.error);
        return;
      }
      setQuickKeyword("");
      setQuickNewBucketName("");
      if (res.data.bucket_created) {
        rememberPendingBucket({ id: res.data.bucket_id, name: res.data.bucket_name });
      }
      setQuickBucketChoice(res.data.bucket_id);
      setBanner({
        kind: "ok",
        text: res.data.created
          ? `Added "${res.data.keyword}" to ${res.data.bucket_name}.`
          : `"${res.data.keyword}" is already on the watchlist in ${res.data.bucket_name}.`,
      });
      router.refresh();
    });
  }

  function openAddDrawer(presetBucketId?: string) {
    setEditingKeyword(null);
    setEditingOriginBucketId(null);
    setKwInput("");
    const fallbackBucket = presetBucketId ?? availableBuckets[0]?.id ?? NEW_BUCKET_VALUE;
    setKwBucketChoice(fallbackBucket);
    setKwNewBucketName(availableBuckets.length === 0 ? "General" : "");
    setShowOptionalMetadata(false);
    setKwVolume("");
    setKwDifficulty("");
    setKwIntent("");
    setKwPrompt("");
    setKwNotes("");
    setDrawerError(null);
    setDrawerOpen(true);
  }

  function openEditDrawer(bucket: WatchlistBucket, kw: WatchlistKeyword) {
    setEditingKeyword(kw);
    setEditingOriginBucketId(bucket.id);
    setKwInput(kw.keyword);
    setKwBucketChoice(bucket.id);
    setKwNewBucketName("");
    const hasMetadata =
      kw.volume !== null ||
      kw.difficulty !== null ||
      Boolean(kw.intent?.trim()) ||
      Boolean(kw.paired_ai_prompt?.trim()) ||
      Boolean(kw.notes?.trim());
    setShowOptionalMetadata(hasMetadata);
    setKwVolume(kw.volume !== null ? String(kw.volume) : "");
    setKwDifficulty(kw.difficulty !== null ? String(kw.difficulty) : "");
    setKwIntent(kw.intent ?? "");
    setKwPrompt(kw.paired_ai_prompt ?? "");
    setKwNotes(kw.notes ?? "");
    setDrawerError(null);
    setDrawerOpen(true);
  }

  function parseOptionalInt(raw: string, label: string, min: number, max?: number): number | null {
    const trimmed = raw.trim();
    if (!trimmed) return null;
    const num = Number(trimmed);
    if (!Number.isInteger(num) || num < min || (max !== undefined && num > max)) {
      throw new Error(
        max !== undefined
          ? `${label} must be a whole number between ${min} and ${max}.`
          : `${label} must be a whole number >= ${min}.`,
      );
    }
    return num;
  }

  function handleSaveKeyword(event: React.FormEvent) {
    event.preventDefault();
    setDrawerError(null);

    const trimmedKw = kwInput.trim().replace(/\s+/g, " ");
    if (!trimmedKw) {
      setDrawerError("Keyword cannot be blank.");
      return;
    }

    let volumeVal: number | null;
    let diffVal: number | null;
    try {
      volumeVal = parseOptionalInt(kwVolume, "Volume", 0, 2147483647);
      diffVal = parseOptionalInt(kwDifficulty, "KD", 0, 100);
    } catch (err) {
      setDrawerError(err instanceof Error ? err.message : "Invalid numeric field.");
      return;
    }

    const useNewBucket = kwBucketChoice === NEW_BUCKET_VALUE;
    const trimmedNewBucket = kwNewBucketName.trim().replace(/\s+/g, " ");
    if (useNewBucket && !trimmedNewBucket) {
      setDrawerError("Enter a name for the new bucket.");
      return;
    }

    const intentVal = kwIntent.trim().replace(/\s+/g, " ") || null;
    const promptVal = kwPrompt.trim() || null;
    const notesVal = kwNotes.trim() || null;

    startTransition(async () => {
      if (editingKeyword === null) {
        const payload: WatchlistKeywordCreateInput = {
          keyword: trimmedKw,
          ...(useNewBucket
            ? { bucket_name: trimmedNewBucket }
            : { bucket_id: kwBucketChoice || null }),
          volume: volumeVal,
          difficulty: diffVal,
          intent: intentVal,
          paired_ai_prompt: promptVal,
          notes: notesVal,
        };
        const res = await addKeywordAction(clientId, clientSlug, payload);
        if (!res.ok) {
          setDrawerError(res.error);
          return;
        }
        if (res.data.bucket_created) {
          rememberPendingBucket({ id: res.data.bucket_id, name: res.data.bucket_name });
        }
        setDrawerOpen(false);
        setBanner({
          kind: "ok",
          text: res.data.created
            ? `Added "${res.data.keyword}" to ${res.data.bucket_name}.`
            : `"${res.data.keyword}" is already on the watchlist in ${res.data.bucket_name}.`,
        });
        router.refresh();
        return;
      }

      const payload: WatchlistKeywordUpdateInput = {
        keyword: trimmedKw,
        volume: volumeVal,
        difficulty: diffVal,
        intent: intentVal,
        paired_ai_prompt: promptVal,
        notes: notesVal,
      };
      if (useNewBucket) {
        payload.bucket_name = trimmedNewBucket;
      } else if (kwBucketChoice && kwBucketChoice !== editingOriginBucketId) {
        payload.bucket_id = kwBucketChoice;
      }

      const res = await updateKeywordAction(clientId, clientSlug, editingKeyword.id, payload);
      if (!res.ok) {
        setDrawerError(res.error);
        return;
      }
      if (useNewBucket && !availableBuckets.some((b) => b.id === res.data.bucket_id)) {
        rememberPendingBucket({ id: res.data.bucket_id, name: res.data.bucket_name });
      }
      setDrawerOpen(false);
      setBanner({ kind: "ok", text: `Saved changes to "${res.data.keyword}".` });
      router.refresh();
    });
  }

  function handleDeleteKeyword(kw: WatchlistKeyword) {
    setBanner(null);
    startTransition(async () => {
      const res = await deleteKeywordAction(clientId, clientSlug, kw.id);
      if (!res.ok) {
        setBanner({ kind: "error", text: res.error });
        return;
      }
      const deletedKey = normalizeKey(kw.keyword);
      setRecentlyAddedKeys((prev) => {
        if (!prev.has(deletedKey)) return prev;
        const next = new Set(prev);
        next.delete(deletedKey);
        return next;
      });
      setConfirmDeleteKeywordId(null);
      setBanner({ kind: "ok", text: `Removed "${kw.keyword}" from the watchlist.` });
      router.refresh();
    });
  }

  function handleCreateBucket(event: React.FormEvent) {
    event.preventDefault();
    setNewBucketError(null);
    const trimmed = newBucketName.trim().replace(/\s+/g, " ");
    if (!trimmed) {
      setNewBucketError("Bucket name cannot be blank.");
      return;
    }
    startTransition(async () => {
      const res = await createBucketAction(clientId, clientSlug, { name: trimmed });
      if (!res.ok) {
        setNewBucketError(res.error);
        return;
      }
      rememberPendingBucket({
        id: res.data.id,
        name: res.data.name,
        sort_order: res.data.sort_order,
      });
      setNewBucketName("");
      setNewBucketOpen(false);
      setBanner({ kind: "ok", text: `Created bucket "${res.data.name}".` });
      router.refresh();
    });
  }

  function handleRenameBucket(bucketId: string) {
    setRenameBucketError(null);
    const trimmed = renameBucketValue.trim().replace(/\s+/g, " ");
    if (!trimmed) {
      setRenameBucketError("Bucket name cannot be blank.");
      return;
    }
    startTransition(async () => {
      const res = await updateBucketAction(clientId, clientSlug, bucketId, { name: trimmed });
      if (!res.ok) {
        setRenameBucketError(res.error);
        return;
      }
      setRenamingBucketId(null);
      setBanner({ kind: "ok", text: `Renamed bucket to "${res.data.name}".` });
      router.refresh();
    });
  }

  function handleDeleteBucket(bucket: WatchlistBucket) {
    setBanner(null);
    const needsConfirm = bucket.keywords.length > 0;
    startTransition(async () => {
      const res = await deleteBucketAction(clientId, clientSlug, bucket.id, needsConfirm);
      if (!res.ok) {
        setBanner({ kind: "error", text: res.error });
        return;
      }
      setConfirmDeleteBucketId(null);
      if (bucketFilter === bucket.id) setBucketFilter("all");
      setBanner({
        kind: "ok",
        text:
          res.data.deleted_keywords > 0
            ? `Deleted bucket "${bucket.name}" and ${res.data.deleted_keywords} keyword(s).`
            : `Deleted bucket "${bucket.name}".`,
      });
      router.refresh();
    });
  }

  async function reloadSuggestions(nextSearch: string, nextDays: 28 | 90) {
    const reqId = ++suggestionsReqIdRef.current;
    setSuggestionsLoading(true);
    setSuggestionsError(null);
    const res = await fetchWatchlistSuggestionsAction(clientId, {
      search: nextSearch || undefined,
      days: nextDays,
      limit: 30,
    });
    if (reqId !== suggestionsReqIdRef.current) {
      return;
    }
    setSuggestionsLoading(false);
    if (!res.ok) {
      setSuggestionsError(res.error);
      return;
    }
    setSuggestionsData(res.data);
  }

  function openSuggestionsDrawer() {
    if (
      suggBucketChoice === NEW_BUCKET_VALUE &&
      suggNewBucketName === "General" &&
      availableBuckets.length > 0
    ) {
      setSuggBucketChoice(availableBuckets[0].id);
    } else if (
      suggBucketChoice !== NEW_BUCKET_VALUE &&
      !availableBuckets.some((b) => b.id === suggBucketChoice)
    ) {
      setSuggBucketChoice(availableBuckets[0]?.id ?? NEW_BUCKET_VALUE);
    }
    setRecentlyAddedKeys(new Set());
    setSuggestionsOpen(true);
    if (suggestionsData === null) {
      reloadSuggestions(suggActiveSearch, suggDays);
    }
  }

  function resolveSuggestionTargetBucket(): { bucket_id?: string; bucket_name?: string } | null {
    if (suggBucketChoice === NEW_BUCKET_VALUE) {
      const name = suggNewBucketName.trim().replace(/\s+/g, " ");
      if (!name) {
        setSuggestionsError("Enter a target bucket name first.");
        return null;
      }
      return { bucket_name: name };
    }
    if (suggBucketChoice && availableBuckets.some((b) => b.id === suggBucketChoice)) {
      return { bucket_id: suggBucketChoice };
    }
    return { bucket_name: "General" };
  }

  function toggleSuggestionSelection(key: string) {
    setSelectedSuggestionKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  async function handleAddSingleSuggestion(item: WatchlistSuggestion) {
    setSuggestionsError(null);
    const target = resolveSuggestionTargetBucket();
    if (!target) return;

    setAddingSuggestionKey(item.key);
    const res = await addKeywordAction(clientId, clientSlug, {
      keyword: item.query,
      ...target,
    });
    setAddingSuggestionKey(null);
    if (!res.ok) {
      setSuggestionsError(res.error);
      return;
    }

    setRecentlyAddedKeys((prev) => new Set(prev).add(item.key));
    setSelectedSuggestionKeys((prev) => {
      const next = new Set(prev);
      next.delete(item.key);
      return next;
    });
    if (res.data.bucket_created) {
      rememberPendingBucket({ id: res.data.bucket_id, name: res.data.bucket_name });
      setSuggBucketChoice(res.data.bucket_id);
    }
    setBanner({
      kind: "ok",
      text: res.data.created
        ? `Added "${res.data.keyword}" to ${res.data.bucket_name}.`
        : `"${res.data.keyword}" is already in ${res.data.bucket_name}.`,
    });
    router.refresh();
  }

  function handleBulkAddSuggestions() {
    setSuggestionsError(null);
    const target = resolveSuggestionTargetBucket();
    if (!target) return;

    const chosen = visibleSuggestions.filter((s) => selectedSuggestionKeys.has(s.key));
    if (chosen.length === 0) return;

    startTransition(async () => {
      const res = await bulkAddKeywordsAction(
        clientId,
        clientSlug,
        chosen.map((s) => ({ keyword: s.query, ...target })),
      );
      if (!res.ok) {
        setSuggestionsError(res.error);
        return;
      }
      setRecentlyAddedKeys((prev) => {
        const next = new Set(prev);
        for (const item of chosen) next.add(item.key);
        return next;
      });
      setSelectedSuggestionKeys(new Set());
      const createdResult = res.data.results.find((r) => r.bucket_created);
      if (createdResult) {
        rememberPendingBucket({
          id: createdResult.bucket_id,
          name: createdResult.bucket_name,
        });
        setSuggBucketChoice(createdResult.bucket_id);
      }
      setBanner({
        kind: "ok",
        text: `Added ${res.data.created_count} keyword(s) from Search Console${
          res.data.existing_count > 0 ? ` (${res.data.existing_count} already tracked)` : ""
        }.`,
      });
      router.refresh();
      await reloadSuggestions(suggActiveSearch, suggDays);
    });
  }

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="font-[family-name:var(--font-display)] text-lg font-bold">Watchlist</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            {clientName} · {buckets.length} {buckets.length === 1 ? "bucket" : "buckets"} ·{" "}
            {initialWatchlist.keyword_count}{" "}
            {initialWatchlist.keyword_count === 1 ? "keyword" : "keywords"}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => openAddDrawer()}
            className="cursor-pointer rounded-lg bg-[var(--brand-dark)] px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:opacity-90"
          >
            + Add keyword
          </button>
          <button
            type="button"
            onClick={() => {
              setNewBucketOpen((v) => !v);
              setNewBucketError(null);
            }}
            className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-3.5 py-2 text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--background)]"
          >
            + New bucket
          </button>
          <button
            type="button"
            onClick={openSuggestionsDrawer}
            className="cursor-pointer rounded-lg bg-[var(--brand-teal)] px-3.5 py-2 text-xs font-semibold text-white transition-colors hover:bg-[var(--brand-teal-hover)]"
          >
            GSC keyword suggestions
            {visibleSuggestions.length > 0 ? (
              <span className="ml-1.5 rounded-full bg-white/20 px-1.5 py-0.5 text-[11px] tabular-nums">
                {visibleSuggestions.length}
              </span>
            ) : null}
          </button>
          <button
            type="button"
            onClick={() => setImportOpen(true)}
            className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-3.5 py-2 text-xs font-semibold text-[var(--text-primary)] hover:bg-[var(--background)]"
          >
            Import CSV
          </button>
        </div>
      </header>

      <form
        onSubmit={handleQuickAdd}
        className="rounded-xl border border-[var(--border)] bg-[var(--surface)] px-4 py-3"
      >
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="text"
            maxLength={400}
            value={quickKeyword}
            onChange={(e) => {
              setQuickKeyword(e.target.value);
              if (quickError) setQuickError(null);
            }}
            placeholder="Quick-add a keyword (e.g. mineral sunscreen)…"
            aria-label="Quick-add keyword"
            className="min-w-[200px] flex-1 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-teal)]"
          />
          <select
            value={effectiveQuickBucket}
            onChange={(e) => {
              setQuickBucketChoice(e.target.value);
              if (quickError) setQuickError(null);
            }}
            aria-label="Quick-add bucket"
            className="rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm"
          >
            {availableBuckets.length === 0 ? <option value="">General</option> : null}
            {availableBuckets.map((b) => (
              <option key={b.id} value={b.id}>
                {b.name}
              </option>
            ))}
            <option value={NEW_BUCKET_VALUE}>Create new bucket…</option>
          </select>
          {effectiveQuickBucket === NEW_BUCKET_VALUE ? (
            <input
              type="text"
              maxLength={160}
              value={quickNewBucketName}
              onChange={(e) => {
                setQuickNewBucketName(e.target.value);
                if (quickError) setQuickError(null);
              }}
              placeholder="New bucket name"
              aria-label="New quick-add bucket name"
              className="w-44 rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-teal)]"
            />
          ) : null}
          <button
            type="submit"
            disabled={pending || !quickKeyword.trim()}
            className="cursor-pointer rounded-lg bg-[var(--brand-dark)] px-4 py-1.5 text-sm font-semibold text-white transition-colors hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            + Add
          </button>
        </div>
        {quickError ? (
          <p role="alert" className="mt-2 text-xs font-medium text-red-700">
            {quickError}
          </p>
        ) : null}
      </form>

      {banner ? (
        <div
          role={banner.kind === "error" ? "alert" : "status"}
          aria-live="polite"
          className={`flex items-center justify-between gap-3 rounded-lg border px-4 py-2.5 text-sm ${
            banner.kind === "error"
              ? "border-red-200 bg-red-50 text-red-800"
              : "border-[#c6f2ed] bg-[#e6f7f5] text-[#00665f]"
          }`}
        >
          <span>{banner.text}</span>
          <button
            type="button"
            onClick={() => setBanner(null)}
            aria-label="Dismiss message"
            className="cursor-pointer text-xs font-semibold opacity-70 hover:opacity-100"
          >
            ✕
          </button>
        </div>
      ) : null}

      {newBucketOpen ? (
        <form
          onSubmit={handleCreateBucket}
          className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-4"
        >
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-[240px] flex-1">
              <Field label="New bucket name">
                <input
                  type="text"
                  maxLength={160}
                  value={newBucketName}
                  onChange={(e) => setNewBucketName(e.target.value)}
                  placeholder="e.g. Core Services"
                  className={inputClass}
                  autoFocus
                />
              </Field>
            </div>
            <button
              type="submit"
              disabled={pending}
              className="cursor-pointer rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Create bucket
            </button>
            <button
              type="button"
              onClick={() => {
                setNewBucketOpen(false);
                setNewBucketError(null);
              }}
              className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold"
            >
              Cancel
            </button>
          </div>
          {newBucketError ? (
            <p role="alert" className="mt-2 text-xs font-medium text-red-700">
              {newBucketError}
            </p>
          ) : null}
        </form>
      ) : null}

      {buckets.length > 0 ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-1.5">
            <button
              type="button"
              onClick={() => setBucketFilter("all")}
              className={`cursor-pointer rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                bucketFilter === "all"
                  ? "bg-[var(--brand-dark)] text-white"
                  : "border border-[var(--border)] bg-white text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              All ({initialWatchlist.keyword_count})
            </button>
            {buckets.map((b) => (
              <button
                key={b.id}
                type="button"
                onClick={() => setBucketFilter(b.id)}
                className={`cursor-pointer rounded-full px-3 py-1 text-xs font-semibold transition-colors ${
                  bucketFilter === b.id
                    ? "bg-[var(--brand-dark)] text-white"
                    : "border border-[var(--border)] bg-white text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {b.name} ({b.keywords.length})
              </button>
            ))}
          </div>

          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Find keyword, intent, prompt, or note…"
            aria-label="Filter watchlist keywords"
            className="w-full rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm sm:w-72 focus:outline-none focus:ring-2 focus:ring-[var(--brand-teal)]"
          />
        </div>
      ) : null}

      {buckets.length === 0 ? (
        <div className="rounded-xl border border-dashed border-[var(--border)] bg-[var(--surface)] p-8 text-center">
          <p className="text-sm font-semibold text-[var(--text-primary)]">
            No buckets or keywords on this watchlist yet.
          </p>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Add keywords manually, pull opportunities from Google Search Console, or import a CSV.
          </p>
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            <button
              type="button"
              onClick={() => openAddDrawer()}
              className="cursor-pointer rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-xs font-semibold text-white"
            >
              + Add first keyword
            </button>
            <button
              type="button"
              onClick={openSuggestionsDrawer}
              className="cursor-pointer rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-xs font-semibold text-white"
            >
              GSC keyword suggestions
            </button>
            <button
              type="button"
              onClick={() => setImportOpen(true)}
              className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-xs font-semibold text-[var(--text-primary)]"
            >
              Import CSV
            </button>
          </div>
        </div>
      ) : filteredBuckets.length === 0 ? (
        <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-6 text-center text-sm text-[var(--text-secondary)]">
          No keywords match “{searchQuery}”.
        </div>
      ) : (
        filteredBuckets.map((bucket) => {
          const fullBucket = buckets.find((b) => b.id === bucket.id) ?? bucket;
          const totalInBucket = fullBucket.keywords.length;
          const showVolume = bucket.keywords.some((row) => row.volume !== null);
          const showDifficulty = bucket.keywords.some((row) => row.difficulty !== null);
          const showIntent = bucket.keywords.some((row) => Boolean(row.intent?.trim()));
          const showPrompt = bucket.keywords.some((row) => Boolean(row.paired_ai_prompt?.trim()));
          return (
          <div
            key={bucket.id}
            className="rounded-xl border border-[var(--border)] bg-[var(--surface)]"
          >
            <div className="border-b border-[var(--border)] px-5 py-3">
              {renamingBucketId === bucket.id ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    handleRenameBucket(bucket.id);
                  }}
                  className="space-y-2"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="text"
                      maxLength={160}
                      value={renameBucketValue}
                      onChange={(e) => setRenameBucketValue(e.target.value)}
                      aria-label={`Rename bucket ${bucket.name}`}
                      className="max-w-xs rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-teal)]"
                      autoFocus
                    />
                    <button
                      type="submit"
                      disabled={pending}
                      className="cursor-pointer rounded-lg bg-[var(--brand-dark)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRenamingBucketId(null);
                        setRenameBucketError(null);
                      }}
                      className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-xs font-semibold"
                    >
                      Cancel
                    </button>
                  </div>
                  {renameBucketError ? (
                    <p role="alert" className="text-xs font-medium text-red-700">
                      {renameBucketError}
                    </p>
                  ) : null}
                </form>
              ) : (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-semibold">
                    {bucket.name}{" "}
                    <span className="font-normal text-[var(--text-tertiary)]">
                      · {bucket.keywords.length}{" "}
                      {bucket.keywords.length === 1 ? "keyword" : "keywords"}
                    </span>
                  </h3>
                  <div className="flex flex-wrap items-center gap-3 text-xs font-semibold">
                    <button
                      type="button"
                      onClick={() => openAddDrawer(bucket.id)}
                      className="cursor-pointer text-[var(--brand-teal)] hover:underline"
                    >
                      + Add keyword
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setRenamingBucketId(bucket.id);
                        setRenameBucketValue(bucket.name);
                        setRenameBucketError(null);
                        setConfirmDeleteBucketId(null);
                      }}
                      className="cursor-pointer text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                    >
                      Rename
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setConfirmDeleteBucketId((cur) => (cur === bucket.id ? null : bucket.id))
                      }
                      className="cursor-pointer text-red-700 hover:underline"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              )}

              {confirmDeleteBucketId === bucket.id ? (
                <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 text-xs text-red-900">
                  <span>
                    {totalInBucket > 0
                      ? `Delete "${bucket.name}" and all ${totalInBucket} keyword(s) inside it? Any monthly focus using this bucket will keep its focus without a bucket.`
                      : `Delete empty bucket "${bucket.name}"?`}
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={pending}
                      onClick={() => handleDeleteBucket(fullBucket)}
                      className="cursor-pointer rounded-lg bg-red-700 px-3 py-1.5 font-semibold text-white hover:bg-red-800 disabled:opacity-50"
                    >
                      Confirm delete
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDeleteBucketId(null)}
                      className="cursor-pointer rounded-lg border border-red-200 bg-white px-3 py-1.5 font-semibold text-[var(--text-primary)]"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
            </div>

            {bucket.keywords.length === 0 ? (
              <div className="flex items-center justify-between px-5 py-4 text-sm text-[var(--text-secondary)]">
                <span>No keywords in this bucket yet.</span>
                <button
                  type="button"
                  onClick={() => openAddDrawer(bucket.id)}
                  className="cursor-pointer text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                >
                  + Add keyword
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-[var(--text-tertiary)]">
                    <tr>
                      <th className="px-5 py-2 font-medium">Keyword</th>
                      {showVolume ? (
                        <th className="px-3 py-2 text-right font-medium">Volume</th>
                      ) : null}
                      {showDifficulty ? (
                        <th className="px-3 py-2 text-right font-medium">KD</th>
                      ) : null}
                      {showIntent ? <th className="px-3 py-2 font-medium">Intent</th> : null}
                      {showPrompt ? (
                        <th className="px-4 py-2 font-medium">Paired AI prompt</th>
                      ) : null}
                      <th className="px-5 py-2 text-right font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {bucket.keywords.map((row) => (
                      <tr key={row.id} className="border-t border-[var(--border)] align-top">
                        <td className="px-5 py-2.5">
                          <div className="font-medium text-[var(--text-primary)]">
                            {row.keyword}
                          </div>
                          {row.notes ? (
                            <div className="mt-0.5 text-xs text-[var(--text-secondary)]">
                              {row.notes}
                            </div>
                          ) : null}
                        </td>
                        {showVolume ? (
                          <td className="px-3 py-2.5 text-right tabular-nums">
                            {row.volume?.toLocaleString() ?? "–"}
                          </td>
                        ) : null}
                        {showDifficulty ? (
                          <td className="px-3 py-2.5 text-right tabular-nums">
                            {row.difficulty ?? "–"}
                          </td>
                        ) : null}
                        {showIntent ? (
                          <td className="px-3 py-2.5 text-[var(--text-secondary)]">
                            {row.intent ?? "–"}
                          </td>
                        ) : null}
                        {showPrompt ? (
                          <td className="max-w-xs px-4 py-2.5 text-[var(--text-secondary)]">
                            {row.paired_ai_prompt ?? "–"}
                          </td>
                        ) : null}
                        <td className="whitespace-nowrap px-5 py-2.5 text-right text-xs font-semibold">
                          {confirmDeleteKeywordId === row.id ? (
                            <span className="inline-flex items-center gap-2">
                              <button
                                type="button"
                                disabled={pending}
                                onClick={() => handleDeleteKeyword(row)}
                                className="cursor-pointer rounded bg-red-700 px-2 py-1 text-white disabled:opacity-50"
                              >
                                Confirm
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirmDeleteKeywordId(null)}
                                className="cursor-pointer text-[var(--text-secondary)] hover:underline"
                              >
                                Cancel
                              </button>
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-3">
                              <button
                                type="button"
                                onClick={() => openEditDrawer(bucket, row)}
                                className="cursor-pointer text-[var(--brand-teal)] hover:underline"
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={() => setConfirmDeleteKeywordId(row.id)}
                                className="cursor-pointer text-red-700 hover:underline"
                              >
                                Delete
                              </button>
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          );
        })
      )}

      {/* Keyword Add / Edit Drawer */}
      {drawerOpen ? (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/30"
          role="dialog"
          aria-modal="true"
          aria-label={editingKeyword ? "Edit keyword" : "Add keyword"}
        >
          <div className="flex h-full w-full max-w-lg flex-col border-l border-[var(--border)] bg-white">
            <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] px-6 py-4">
              <div>
                <h2 className="font-[family-name:var(--font-display)] text-lg font-bold">
                  {editingKeyword ? "Edit keyword" : "Add keyword"}
                </h2>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  {editingKeyword
                    ? "Update keyword or move it to another bucket. Blank optional fields clear stored values."
                    : "Enter a keyword and pick a bucket. Optional metadata can be added below if needed."}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setDrawerOpen(false)}
                aria-label="Close keyword drawer"
                className="cursor-pointer rounded-full border border-[var(--border)] px-2.5 py-1 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={handleSaveKeyword}
              className="flex flex-1 flex-col justify-between overflow-y-auto px-6 py-5"
            >
              <div className="space-y-4">
                {drawerError ? (
                  <p role="alert" className="rounded-lg bg-red-50 p-3 text-xs text-red-800">
                    {drawerError}
                  </p>
                ) : null}

                <Field label="Keyword *">
                  <input
                    type="text"
                    maxLength={400}
                    value={kwInput}
                    onChange={(e) => setKwInput(e.target.value)}
                    placeholder="e.g. mineral sunscreen"
                    className={inputClass}
                    required
                    autoFocus
                  />
                </Field>

                <Field label="Bucket">
                  <select
                    value={kwBucketChoice}
                    onChange={(e) => setKwBucketChoice(e.target.value)}
                    className={inputClass}
                  >
                    {availableBuckets.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                    <option value={NEW_BUCKET_VALUE}>Create new bucket…</option>
                  </select>
                </Field>

                {kwBucketChoice === NEW_BUCKET_VALUE ? (
                  <Field label="New bucket name *">
                    <input
                      type="text"
                      maxLength={160}
                      value={kwNewBucketName}
                      onChange={(e) => setKwNewBucketName(e.target.value)}
                      placeholder="e.g. General"
                      className={inputClass}
                    />
                  </Field>
                ) : null}

                <div className="border-t border-[var(--border)] pt-3">
                  <button
                    type="button"
                    onClick={() => setShowOptionalMetadata((v) => !v)}
                    aria-expanded={showOptionalMetadata}
                    className="flex w-full cursor-pointer items-center justify-between text-left text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                  >
                    <span>Optional metadata (volume, KD, intent, AI prompt, notes)</span>
                    <span>{showOptionalMetadata ? "Hide" : "Show"}</span>
                  </button>
                </div>

                {showOptionalMetadata ? (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Volume" hint="Monthly search volume">
                        <input
                          type="number"
                          min={0}
                          max={2147483647}
                          value={kwVolume}
                          onChange={(e) => setKwVolume(e.target.value)}
                          placeholder="e.g. 2400"
                          className={inputClass}
                        />
                      </Field>
                      <Field label="KD" hint="0–100 difficulty">
                        <input
                          type="number"
                          min={0}
                          max={100}
                          value={kwDifficulty}
                          onChange={(e) => setKwDifficulty(e.target.value)}
                          placeholder="0–100"
                          className={inputClass}
                        />
                      </Field>
                    </div>

                    <Field label="Intent">
                      <input
                        type="text"
                        list="watchlist-intent-options"
                        maxLength={120}
                        value={kwIntent}
                        onChange={(e) => setKwIntent(e.target.value)}
                        placeholder="e.g. Commercial"
                        className={inputClass}
                      />
                      <datalist id="watchlist-intent-options">
                        <option value="Informational" />
                        <option value="Commercial" />
                        <option value="Transactional" />
                        <option value="Navigational" />
                      </datalist>
                    </Field>

                    <Field label="Paired AI prompt">
                      <textarea
                        rows={2}
                        maxLength={4000}
                        value={kwPrompt}
                        onChange={(e) => setKwPrompt(e.target.value)}
                        placeholder="Prompt checked during LLM visibility runs"
                        className={inputClass}
                      />
                    </Field>

                    <Field label="Notes">
                      <textarea
                        rows={2}
                        maxLength={4000}
                        value={kwNotes}
                        onChange={(e) => setKwNotes(e.target.value)}
                        placeholder="Internal context or prioritization notes"
                        className={inputClass}
                      />
                    </Field>
                  </div>
                ) : null}
              </div>

              <div className="mt-6 flex items-center justify-end gap-2 border-t border-[var(--border)] pt-4">
                <button
                  type="button"
                  onClick={() => setDrawerOpen(false)}
                  className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={pending}
                  className="cursor-pointer rounded-lg bg-[var(--brand-dark)] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  {pending
                    ? "Saving…"
                    : editingKeyword
                      ? "Save changes"
                      : "Add keyword"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {/* GSC Keyword Suggestions Drawer */}
      {suggestionsOpen ? (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/30"
          role="dialog"
          aria-modal="true"
          aria-label="GSC keyword suggestions"
        >
          <div className="flex h-full w-full max-w-2xl flex-col border-l border-[var(--border)] bg-white">
            <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] px-6 py-4">
              <div>
                <h2 className="font-[family-name:var(--font-display)] text-lg font-bold">
                  GSC keyword suggestions
                </h2>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Untracked, non-brand Search Console queries
                  {suggestionsData?.google_through
                    ? ` · data through ${suggestionsData.google_through}`
                    : ""}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSuggestionsOpen(false)}
                aria-label="Close suggestions drawer"
                className="cursor-pointer rounded-full border border-[var(--border)] px-2.5 py-1 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                ✕
              </button>
            </div>

            <div className="border-b border-[var(--border)] bg-[var(--background)] px-6 py-3.5 space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    setSuggActiveSearch(suggSearchInput);
                    reloadSuggestions(suggSearchInput, suggDays);
                  }}
                  className="flex flex-1 items-center gap-2"
                >
                  <input
                    type="search"
                    value={suggSearchInput}
                    onChange={(e) => setSuggSearchInput(e.target.value)}
                    placeholder="Search Search Console queries…"
                    aria-label="Search GSC suggestions"
                    className="w-full rounded-lg border border-[var(--border)] bg-white px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-[var(--brand-teal)]"
                  />
                  <button
                    type="submit"
                    disabled={suggestionsLoading}
                    className="cursor-pointer rounded-lg bg-[var(--brand-dark)] px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                  >
                    Search
                  </button>
                  {suggActiveSearch ? (
                    <button
                      type="button"
                      onClick={() => {
                        setSuggSearchInput("");
                        setSuggActiveSearch("");
                        reloadSuggestions("", suggDays);
                      }}
                      className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-2.5 py-1.5 text-xs font-semibold"
                    >
                      Clear
                    </button>
                  ) : null}
                </form>

                <div className="inline-flex rounded-lg border border-[var(--border)] bg-white p-0.5 text-xs font-semibold">
                  {([28, 90] as const).map((d) => (
                    <button
                      key={d}
                      type="button"
                      onClick={() => {
                        setSuggDays(d);
                        reloadSuggestions(suggActiveSearch, d);
                      }}
                      className={`cursor-pointer rounded-md px-2.5 py-1 ${
                        suggDays === d
                          ? "bg-[var(--brand-dark)] text-white"
                          : "text-[var(--text-secondary)]"
                      }`}
                    >
                      {d}d
                    </button>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="font-semibold text-[var(--text-secondary)]">Add to bucket:</span>
                <select
                  value={suggBucketChoice}
                  onChange={(e) => setSuggBucketChoice(e.target.value)}
                  aria-label="Target bucket for suggestions"
                  className="rounded-lg border border-[var(--border)] bg-white px-2.5 py-1 text-xs font-medium"
                >
                  {availableBuckets.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
                  <option value={NEW_BUCKET_VALUE}>Create new bucket…</option>
                </select>
                {suggBucketChoice === NEW_BUCKET_VALUE ? (
                  <input
                    type="text"
                    maxLength={160}
                    value={suggNewBucketName}
                    onChange={(e) => setSuggNewBucketName(e.target.value)}
                    placeholder="New bucket name"
                    aria-label="New target bucket name"
                    className="rounded-lg border border-[var(--border)] bg-white px-2.5 py-1 text-xs"
                  />
                ) : null}
              </div>

              {suggestionsError ? (
                <p role="alert" className="rounded-lg bg-red-50 p-2.5 text-xs text-red-800">
                  {suggestionsError}
                </p>
              ) : null}
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-4">
              {suggestionsLoading ? (
                <p className="py-8 text-center text-sm text-[var(--text-secondary)]">
                  Loading Search Console suggestions…
                </p>
              ) : suggestionsData === null ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 text-sm">
                  <p className="font-semibold">Could not load Search Console suggestions.</p>
                  <button
                    type="button"
                    onClick={() => reloadSuggestions(suggActiveSearch, suggDays)}
                    className="mt-3 cursor-pointer rounded-lg bg-[var(--brand-dark)] px-3.5 py-1.5 text-xs font-semibold text-white"
                  >
                    Retry
                  </button>
                </div>
              ) : !suggestionsData.gsc_connected ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 text-sm">
                  <p className="font-semibold text-[var(--text-primary)]">
                    Google Search Console is not connected for this client.
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    Connect Search Console to discover untracked non-brand queries ranked by
                    impressions and growth.
                  </p>
                  <Link
                    href={`/${clientSlug}/settings/connections`}
                    className="mt-3 inline-block text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                  >
                    Connect Search Console →
                  </Link>
                </div>
              ) : !suggestionsData.has_gsc_data ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 text-sm">
                  <p className="font-semibold text-[var(--text-primary)]">
                    Search Console is connected, but no query data has been synced yet.
                  </p>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">
                    Run a Search Console sync from Connections to populate keyword suggestions.
                  </p>
                  <Link
                    href={`/${clientSlug}/settings/connections`}
                    className="mt-3 inline-block text-xs font-semibold text-[var(--brand-teal)] hover:underline"
                  >
                    Go to Connections →
                  </Link>
                </div>
              ) : visibleSuggestions.length === 0 ? (
                <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 text-sm text-[var(--text-secondary)]">
                  No untracked non-brand Search Console opportunities matched your filter.
                </div>
              ) : (
                <ul className="space-y-2.5">
                  {visibleSuggestions.map((s) => {
                    const isAdded = recentlyAddedKeys.has(s.key);
                    const isChecked = selectedSuggestionKeys.has(s.key);
                    const isAdding = addingSuggestionKey === s.key;
                    return (
                      <li
                        key={s.key}
                        className="flex items-start justify-between gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface)] p-3.5"
                      >
                        <div className="flex min-w-0 items-start gap-3">
                          <input
                            type="checkbox"
                            checked={isChecked}
                            disabled={isAdded || isAdding}
                            onChange={() => toggleSuggestionSelection(s.key)}
                            aria-label={`Select ${s.query}`}
                            className="mt-1 h-4 w-4 rounded border-[var(--border)] accent-[var(--brand-teal)]"
                          />
                          <div className="min-w-0 space-y-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <span className="font-semibold text-sm text-[var(--text-primary)]">
                                {s.query}
                              </span>
                              {s.signals.map((sig) => {
                                const badge = SIGNAL_LABELS[sig] ?? {
                                  label: sig,
                                  cls: "bg-[#eef0f1] text-[#223540]",
                                };
                                return (
                                  <span
                                    key={sig}
                                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge.cls}`}
                                  >
                                    {badge.label}
                                  </span>
                                );
                              })}
                            </div>
                            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--text-secondary)] tabular-nums">
                              <span>{s.impressions.toLocaleString()} impr</span>
                              {s.impressions_change_pct !== null ? (
                                <span className="text-[#00665f]">
                                  {s.impressions_change_pct >= 0 ? "+" : ""}
                                  {s.impressions_change_pct}%
                                </span>
                              ) : null}
                              <span>{s.clicks.toLocaleString()} clicks</span>
                              <span>
                                {s.position !== null ? `#${s.position.toFixed(1)}` : "pos –"}
                              </span>
                              <span>{s.ctr !== null ? `${s.ctr.toFixed(1)}% CTR` : "CTR –"}</span>
                              {s.page ? (
                                <span className="truncate text-[var(--text-tertiary)]">
                                  {shortPath(s.page)}
                                </span>
                              ) : null}
                            </div>
                            <p className="text-xs text-[var(--text-tertiary)]">
                              {s.relevance_note}
                            </p>
                          </div>
                        </div>

                        <button
                          type="button"
                          disabled={isAdded || isAdding || pending}
                          onClick={() => handleAddSingleSuggestion(s)}
                          className={`shrink-0 cursor-pointer rounded-lg px-3 py-1.5 text-xs font-semibold ${
                            isAdded
                              ? "bg-[#e6f7f5] text-[#00665f]"
                              : "bg-[var(--brand-dark)] text-white hover:opacity-90 disabled:opacity-50"
                          }`}
                        >
                          {isAdded ? "Added ✓" : isAdding ? "Adding…" : "Add"}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {selectedSuggestionKeys.size > 0 ? (
              <div className="flex items-center justify-between gap-3 border-t border-[var(--border)] bg-[var(--background)] px-6 py-3">
                <span className="text-xs font-semibold text-[var(--text-secondary)]">
                  {selectedSuggestionKeys.size} selected
                </span>
                <button
                  type="button"
                  disabled={pending}
                  onClick={handleBulkAddSuggestions}
                  className="cursor-pointer rounded-lg bg-[var(--brand-teal)] px-4 py-2 text-xs font-semibold text-white hover:bg-[var(--brand-teal-hover)] disabled:opacity-50"
                >
                  {pending
                    ? "Adding…"
                    : `Add ${selectedSuggestionKeys.size} selected`}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Embedded CSV Import Drawer */}
      {importOpen ? (
        <div
          className="fixed inset-0 z-50 flex justify-end bg-black/30"
          role="dialog"
          aria-modal="true"
          aria-label="Import watchlist from CSV"
        >
          <div className="flex h-full w-full max-w-xl flex-col border-l border-[var(--border)] bg-white">
            <div className="flex items-start justify-between gap-4 border-b border-[var(--border)] px-6 py-4">
              <div>
                <h2 className="font-[family-name:var(--font-display)] text-lg font-bold">
                  Import from CSV
                </h2>
                <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                  Add or update watchlist keywords from a CSV export without leaving this page.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setImportOpen(false)}
                aria-label="Close CSV import drawer"
                className="cursor-pointer rounded-full border border-[var(--border)] px-2.5 py-1 text-xs font-semibold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto px-6 py-5">
              <WatchlistImport
                clientId={clientId}
                slug={clientSlug}
                embedded
                onImported={(report: ImportReport) => {
                  setBanner({
                    kind: "ok",
                    text: `CSV imported: ${report.keywords_created} new keyword(s), ${report.keywords_updated} updated.`,
                  });
                }}
              />
            </div>

            <div className="flex items-center justify-end border-t border-[var(--border)] px-6 py-3">
              <button
                type="button"
                onClick={() => setImportOpen(false)}
                className="cursor-pointer rounded-lg border border-[var(--border)] bg-white px-4 py-2 text-sm font-semibold"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  );
}
