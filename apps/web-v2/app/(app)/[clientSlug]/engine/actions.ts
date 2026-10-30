"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { Allowance, DiagnoseResult, Diagnosis, EngineTask, GrowthActionBundle, TaskDraft, TaskResult, TopicPages } from "@/lib/engine";

export async function diagnoseAction(
  clientId: string,
  selections: { search: string; page: string }[],
): Promise<DiagnoseResult> {
  try {
    const body = await apiFetch<{ results: Diagnosis[] }>("/v2/engine/diagnose", {
      method: "POST",
      clientId,
      body: { selections },
    });
    return { ok: true, results: body.results };
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

export async function updateTaskAction(
  clientId: string,
  id: string,
  patch: {
    status?: "confirmed" | "shipped" | "dropped";
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
  focus: "traffic" | "leads",
  pages: string[],
): Promise<DiagnoseResult> {
  try {
    const body = await apiFetch<{ results: Diagnosis[] }>("/v2/engine/diagnose-page", {
      method: "POST",
      clientId,
      body: { focus, pages },
    });
    return { ok: true, results: body.results };
  } catch (error) {
    return {
      ok: false,
      error: error instanceof ApiError ? error.message : "The pages could not be read: the API did not answer.",
    };
  }
}

export async function topicPagesAction(clientId: string, keyword: string): Promise<TaskResult<TopicPages>> {
  try {
    const value = await apiFetch<TopicPages>(`/v2/engine/topic-pages?keyword=${encodeURIComponent(keyword)}`, { clientId });
    return { ok: true, value };
  } catch (error) {
    return failure(error, "The pages could not be listed: the API did not answer.");
  }
}

export async function buildGrowthActionAction(clientId: string, keyword: string, page: string | null): Promise<GrowthActionBundle> {
  try {
    return await apiFetch<GrowthActionBundle>("/v2/engine/growth-action", { method: "POST", clientId, body: { keyword, page } });
  } catch (error) {
    return { ok: false, error: error instanceof ApiError ? error.message : "The page could not be read: the API did not answer." };
  }
}
