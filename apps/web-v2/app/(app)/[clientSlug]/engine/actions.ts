"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type {
  Allowance,
  CandidateTopic,
  DiagnoseResult,
  Diagnosis,
  EngineKind,
  EngineTask,
  GrowthActionBundle,
  MonthWork,
  PageHistory,
  RejectTaskInput,
  RejectionReason,
  RejectionReasonsResponse,
  SerpLookupResult,
  TaskDraft,
  TaskPartInput,
  TaskPlan,
  TaskResult,
} from "@/lib/engine";

export async function diagnoseAction(
  clientId: string,
  selections: { search: string; page: string }[],
  focus?: EngineKind | null,
  month?: string | null,
): Promise<DiagnoseResult> {
  try {
    const body = await apiFetch<{ month?: string; focus?: EngineKind; results: Diagnosis[] }>("/v2/engine/diagnose", {
      method: "POST",
      clientId,
      body: {
        selections,
        ...(focus ? { focus } : {}),
        ...(month ? { month } : {}),
      },
    });
    return { ok: true, results: body.results, month: body.month, focus: body.focus };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "The pages could not be read: the API did not answer.",
    };
  }
}

function failure(error: unknown, fallback: string): { ok: false; error: string } {
  return { ok: false, error: error instanceof ApiError ? error.message : fallback };
}

export async function rejectionReasonsAction(): Promise<TaskResult<RejectionReason[]>> {
  try {
    const out = await apiFetch<RejectionReasonsResponse>("/v2/engine/rejection-reasons");
    return { ok: true, value: out.reasons };
  } catch (error) {
    return failure(error, "The rejection reasons could not be loaded: the API did not answer.");
  }
}

export async function confirmTaskAction(clientId: string, month: string, draft: TaskDraft): Promise<TaskResult> {
  try {
    const body = await apiFetch<{ task: EngineTask; allowance: Allowance }>("/v2/engine/tasks", {
      method: "POST",
      clientId,
      body: { month, ...draft },
    });
    return { ok: true, value: body.task, allowance: body.allowance };
  } catch (error) {
    return failure(error, "The task could not be saved: the API did not answer.");
  }
}

export async function rejectTaskAction(clientId: string, input: RejectTaskInput): Promise<TaskResult> {
  try {
    const task = await apiFetch<EngineTask>("/v2/engine/tasks/reject", {
      method: "POST",
      clientId,
      body: input,
    });
    return { ok: true, value: task };
  } catch (error) {
    return failure(error, "The rejection could not be saved: the API did not answer.");
  }
}

export async function updateTaskAction(
  clientId: string,
  id: string,
  patch: {
    status?: "confirmed" | "shipped" | "dropped" | "rejected";
    rejection_reason?: string;
    rejection_note?: string;
    steps?: string[];
    parts?: TaskPartInput[];
    assignee_email?: string;
    due?: string;
    clear_assignee?: boolean;
    clear_due?: boolean;
  },
): Promise<TaskResult> {
  try {
    const task = await apiFetch<EngineTask>(`/v2/engine/tasks/${id}`, { method: "PATCH", clientId, body: patch });
    return { ok: true, value: task };
  } catch (error) {
    return failure(error, "The task could not be updated: the API did not answer.");
  }
}

export async function sendTaskAction(clientId: string, id: string): Promise<TaskResult> {
  try {
    const task = await apiFetch<EngineTask>(`/v2/engine/tasks/${id}/send`, { method: "POST", clientId });
    return { ok: true, value: task };
  } catch (error) {
    return failure(error, "The task could not be sent: the API did not answer.");
  }
}

export async function taskTextAction(clientId: string, id: string): Promise<TaskResult<string>> {
  try {
    const out = await apiFetch<{ text: string }>(`/v2/engine/tasks/${id}/text`, { clientId });
    return { ok: true, value: out.text };
  } catch (error) {
    return failure(error, "The text could not be built: the API did not answer.");
  }
}

export async function diagnosePagesAction(
  clientId: string,
  focus: EngineKind | null,
  pages: string[],
  month?: string | null,
): Promise<DiagnoseResult> {
  try {
    const body = await apiFetch<{ month?: string; focus?: EngineKind; results: Diagnosis[] }>("/v2/engine/diagnose-page", {
      method: "POST",
      clientId,
      body: {
        ...(focus ? { focus } : {}),
        ...(month ? { month } : {}),
        pages,
      },
    });
    return { ok: true, results: body.results, month: body.month, focus: body.focus };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "The pages could not be read: the API did not answer.",
    };
  }
}

export async function topicForAction(clientId: string, search: string, page: string): Promise<TaskResult<CandidateTopic>> {
  try {
    const value = await apiFetch<CandidateTopic>(
      `/v2/engine/topic-for?page=${encodeURIComponent(page)}&search=${encodeURIComponent(search)}`,
      { clientId },
    );
    return { ok: true, value };
  } catch (error) {
    return failure(error, "The topic could not be worked out: the API did not answer.");
  }
}

export async function buildGrowthActionAction(
  clientId: string,
  keyword: string,
  page: string | null,
  focus: EngineKind | null,
  candidatePage: string,
  search: string | null = null,
  month?: string | null,
): Promise<GrowthActionBundle> {
  try {
    return await apiFetch<GrowthActionBundle>("/v2/engine/growth-action", {
      method: "POST",
      clientId,
      body: {
        keyword,
        page,
        ...(focus ? { focus } : {}),
        candidate_page: candidatePage,
        search,
        ...(month ? { month } : {}),
      },
    });
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The page could not be read: the API did not answer." };
  }
}

export async function pageHistoryAction(clientId: string, page: string): Promise<TaskResult<PageHistory>> {
  try {
    const value = await apiFetch<PageHistory>(`/v2/engine/page-history?page=${encodeURIComponent(page)}`, { clientId });
    return { ok: true, value };
  } catch (error) {
    return failure(error, "The page history could not be loaded: the API did not answer.");
  }
}

export async function serpLookupAction(
  clientId: string,
  search: string,
  pull = false,
): Promise<TaskResult<SerpLookupResult>> {
  try {
    const query = new URLSearchParams({ search, pull: pull ? "true" : "false" });
    const value = await apiFetch<SerpLookupResult>(`/v2/engine/serp?${query.toString()}`, { clientId });
    return { ok: true, value };
  } catch (error) {
    return failure(error, "The search results could not be loaded: the API did not answer.");
  }
}

export async function pullSerpAction(clientId: string, search: string): Promise<TaskResult<SerpLookupResult>> {
  try {
    const value = await apiFetch<SerpLookupResult>("/v2/engine/serp/pull", {
      method: "POST",
      clientId,
      body: { search },
    });
    return { ok: true, value };
  } catch (error) {
    return failure(error, "The search results could not be pulled: the API did not answer.");
  }
}

export async function workAction(clientId: string, month: string): Promise<MonthWork | null> {
  try {
    return (await apiFetch<TaskPlan>(`/v2/engine/tasks?month=${month}`, { clientId })).work ?? null;
  } catch {
    return null;
  }
}

export async function markPartAction(clientId: string, id: string, index: number, done: boolean): Promise<TaskResult> {
  try {
    const task = await apiFetch<EngineTask>(`/v2/engine/tasks/${id}/parts/${index}`, { method: "PATCH", clientId, body: { done } });
    return { ok: true, value: task };
  } catch (error) {
    return failure(error, "The part could not be updated: the API did not answer.");
  }
}

export async function checkLiveAction(clientId: string, id: string): Promise<{ ok: true; value: { task: EngineTask; check: { checked: number; live: number; unreadable: string | null; teamwork?: { checked: number; marked: number; error: string | null } } } } | { ok: false; error: string }> {
  try {
    return { ok: true, value: await apiFetch(`/v2/engine/tasks/${id}/check`, { method: "POST", clientId }) };
  } catch (error) {
    return failure(error, "The page could not be checked: the API did not answer.");
  }
}
