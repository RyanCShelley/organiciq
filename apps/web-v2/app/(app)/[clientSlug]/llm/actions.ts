"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { LlmResponseRow, LlmResult, LlmSettings } from "@/lib/llm";

function failure(error: unknown, fallback: string): { ok: false; error: string } {
  return { ok: false, error: error instanceof ApiError ? error.message : fallback };
}

export async function startLlmRunAction(clientId: string): Promise<LlmResult<null>> {
  try {
    await apiFetch("/v2/llm/run", { method: "POST", clientId });
    return { ok: true, value: null };
  } catch (error) {
    return failure(error, "The run could not be queued: the API did not answer.");
  }
}

export async function saveLlmSettingsAction(
  clientId: string,
  body: { brand_name: string; brand_patterns: string[]; competitors: { domain: string; name: string; patterns: string[] }[] },
): Promise<LlmResult<LlmSettings>> {
  try {
    return { ok: true, value: await apiFetch<LlmSettings>("/v2/llm/settings", { method: "PUT", clientId, body }) };
  } catch (error) {
    return failure(error, "The settings could not be saved: the API did not answer.");
  }
}

export async function llmResponsesAction(clientId: string, runId: string): Promise<LlmResult<LlmResponseRow[]>> {
  try {
    return { ok: true, value: await apiFetch<LlmResponseRow[]>(`/v2/llm/runs/${runId}/responses`, { clientId }) };
  } catch (error) {
    return failure(error, "The run could not be read: the API did not answer.");
  }
}

export async function addLlmPromptsAction(
  clientId: string,
  prompts: { prompt: string; topic_cluster: string }[],
): Promise<LlmResult<{ added: number; skipped: number; settings: LlmSettings }>> {
  try {
    return { ok: true, value: await apiFetch("/v2/llm/prompts", { method: "POST", clientId, body: { prompts } }) };
  } catch (error) {
    return failure(error, "The prompts could not be saved: the API did not answer.");
  }
}

export type SuggestedGroup = { topic_cluster: string; prompts: string[] };

export async function suggestLlmPromptsAction(clientId: string): Promise<LlmResult<{ platform: string; groups: SuggestedGroup[] }>> {
  try {
    return { ok: true, value: await apiFetch("/v2/llm/prompts/suggest", { method: "POST", clientId }) };
  } catch (error) {
    return failure(error, "Suggestions could not be written: the API did not answer.");
  }
}

export async function removeLlmPromptAction(clientId: string, promptId: string): Promise<LlmResult<LlmSettings>> {
  try {
    return { ok: true, value: await apiFetch<LlmSettings>(`/v2/llm/prompts/${promptId}`, { method: "DELETE", clientId }) };
  } catch (error) {
    return failure(error, "The prompt could not be removed: the API did not answer.");
  }
}
