"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { Brief, ContentDepthChoice, RefreshDetail, SplitSearch, TopicDetail, TopicsResponse } from "@/lib/content";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (error: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export async function briefAction(clientId: string, term: string): Promise<R<Brief | null>> {
  try {
    const q = new URLSearchParams({ term });
    const r = await apiFetch<{ draft: Brief | null }>(`/v2/content/gaps/brief?${q}`, { clientId });
    return { ok: true, value: r.draft };
  } catch (e) {
    return fail(e, "The brief could not be read: the API did not answer.");
  }
}

export async function topicsAction(clientId: string): Promise<R<TopicsResponse>> {
  try {
    return { ok: true, value: await apiFetch<TopicsResponse>("/v2/content/topics", { clientId }) };
  } catch (e) {
    return fail(e, "The topics could not be read: the API did not answer.");
  }
}

export async function topicDetailAction(clientId: string, label: string): Promise<R<TopicDetail>> {
  try {
    const q = new URLSearchParams({ label });
    return { ok: true, value: await apiFetch<TopicDetail>(`/v2/content/topics/detail?${q}`, { clientId }) };
  } catch (e) {
    return fail(e, "The topic could not be read: the API did not answer.");
  }
}

export async function draftAction(clientId: string, kind: "brief" | "refresh" | "topics" | "tbrief", key: string, depth: ContentDepthChoice, month?: string): Promise<R<true>> {
  try {
    await apiFetch("/v2/content/draft", { method: "POST", clientId, body: { kind, key, depth, month } });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "The model could not be asked: the API did not answer.");
  }
}

export async function setAsideAction(clientId: string, area: "gap" | "refresh", key: string, restore: boolean): Promise<R<true>> {
  try {
    await apiFetch(`/v2/content/${restore ? "restore" : "ignore"}`, { method: "POST", clientId, body: { area, key } });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "That could not be saved: the API did not answer.");
  }
}

export async function dismissTopicAction(clientId: string, label: string, restore: boolean): Promise<R<true>> {
  try {
    await apiFetch("/v2/content/topics/dismiss", { method: "POST", clientId, body: { label, restore } });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "That could not be saved: the API did not answer.");
  }
}

export async function refreshPageAction(clientId: string, url: string, month: string): Promise<R<RefreshDetail>> {
  try {
    const q = new URLSearchParams({ url, month });
    return { ok: true, value: await apiFetch<RefreshDetail>(`/v2/content/refreshes/page?${q}`, { clientId }) };
  } catch (e) {
    return fail(e, "The page could not be read: the API did not answer.");
  }
}

export async function splitSearchAction(clientId: string, query: string, month: string): Promise<R<SplitSearch>> {
  try {
    const q = new URLSearchParams({ query, month });
    return { ok: true, value: await apiFetch<SplitSearch>(`/v2/content/refreshes/search?${q}`, { clientId }) };
  } catch (e) {
    return fail(e, "The search could not be read: the API did not answer.");
  }
}
