"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/api";

/**
 * Re-run this month and replace its saved record.
 *
 * The client-page spec removed this button — "re-running lives on the admin
 * board only" — on the argument that a Run button beside a plan invites
 * someone to re-roll an answer they did not like. That call is reversed: the
 * person who fixes a mapping or a sync is the person looking at this page,
 * and sending them elsewhere to see the fix land is the bigger cost.
 *
 * The guard against re-rolling stays where it belongs — in the engine. A run
 * reads the same facts every time, so pressing this twice in a row produces
 * the same answer twice. What changes is the saved timestamp, which the page
 * shows, and `held_since`, which the engine carries forward rather than
 * resetting.
 */
export async function runMonthlyRecordAction(clientId: string, slug: string) {
  if (!clientId) {
    return { ok: false as const, error: "Missing client" };
  }

  try {
    const record = await apiFetch<{ month: string }>("/decisions/records/run", {
      method: "POST",
      clientId,
    });
    revalidatePath(`/${slug}/decision-engine`);
    return { ok: true as const, month: record.month };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "The run failed",
    };
  }
}

type SlotState = {
  uid: string;
  status: string;
  assignee_user_id: string | null;
  due: string | null;
  skip_reason: string | null;
  sent_at: string | null;
  teamwork_task_id: string | null;
  teamwork_task_url: string | null;
  stale: boolean;
};

type SlotResult =
  | { ok: true; state: SlotState }
  | { ok: false; error: string };

async function slotPost(
  clientId: string,
  slug: string,
  path: string,
  body: unknown,
): Promise<SlotResult> {
  if (!clientId) return { ok: false as const, error: "Missing client" };
  try {
    const state = await apiFetch<SlotState>(path, {
      method: "POST",
      clientId,
      body,
    });
    revalidatePath(`/${slug}/decision-engine`);
    return { ok: true as const, state };
  } catch (e) {
    return {
      ok: false as const,
      error: e instanceof Error ? e.message : "That did not save",
    };
  }
}

/** Hand a slot to somebody. An empty assignee returns it to planned. */
export async function assignSlotAction(input: {
  clientId: string;
  slug: string;
  month: string;
  uid: string;
  assigneeUserId: string | null;
  due: string | null;
}): Promise<SlotResult> {
  return slotPost(
    input.clientId,
    input.slug,
    `/decisions/records/${encodeURIComponent(input.month)}/slots/${encodeURIComponent(input.uid)}/assign`,
    { assignee_user_id: input.assigneeUserId || null, due: input.due || null },
  );
}

/** Take a slot off the table, with the reason on the record — or put it back. */
export async function skipSlotAction(input: {
  clientId: string;
  slug: string;
  month: string;
  uid: string;
  reason?: string;
  undo?: boolean;
}): Promise<SlotResult> {
  return slotPost(
    input.clientId,
    input.slug,
    `/decisions/records/${encodeURIComponent(input.month)}/slots/${encodeURIComponent(input.uid)}/skip`,
    { reason: input.reason ?? null, undo: Boolean(input.undo) },
  );
}

/** Push the slot to Teamwork. Idempotent: a second press links the existing task. */
export async function sendSlotAction(input: {
  clientId: string;
  slug: string;
  month: string;
  uid: string;
}): Promise<SlotResult> {
  return slotPost(
    input.clientId,
    input.slug,
    `/decisions/records/${encodeURIComponent(input.month)}/slots/${encodeURIComponent(input.uid)}/send`,
    {},
  );
}
