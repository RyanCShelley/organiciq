"use server";

import { apiFetch, ApiError } from "@/lib/api";

export type CopilotReply = {
  conversation_id: string;
  message_id: string;
  reply: string;
  rounds: number;
  incomplete: boolean;
};

export type CopilotAskResult =
  | ({ ok: true } & CopilotReply)
  | { ok: false; error: string };

export async function askCopilotAction(
  clientId: string,
  message: string,
  conversationId: string | null,
): Promise<CopilotAskResult> {
  const text = message.trim();
  if (!clientId) return { ok: false, error: "Missing client" };
  if (!text) return { ok: false, error: "Type a question first." };

  try {
    const reply = await apiFetch<CopilotReply>("/copilot/chat", {
      method: "POST",
      clientId,
      body: { message: text, conversation_id: conversationId },
    });
    return { ok: true, ...reply };
  } catch (e) {
    if (e instanceof ApiError && e.status === 503) {
      return { ok: false, error: "The copilot is not configured yet. Set LLM_BASE_URL on the API." };
    }
    if (e instanceof ApiError && e.status === 502) {
      return { ok: false, error: "The model could not be reached. Try again in a moment." };
    }
    return { ok: false, error: e instanceof Error ? e.message : "Something went wrong." };
  }
}

export async function rateCopilotMessageAction(
  clientId: string,
  messageId: string,
  rating: 1 | -1 | 0,
  correction?: string,
): Promise<{ ok: boolean; error?: string }> {
  if (!clientId || !messageId) return { ok: false, error: "Missing id" };
  try {
    await apiFetch(`/copilot/messages/${messageId}/rating`, {
      method: "POST",
      clientId,
      body: { rating, correction: correction?.trim() || null },
    });
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : "Could not save the rating." };
  }
}
