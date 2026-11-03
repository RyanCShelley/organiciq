"use server";

import { ApiError, apiFetch } from "@/lib/api";
import type { CalendarData, CalendarItem, CalendarStatus, Person } from "@/lib/content";

type R<T> = { ok: true; value: T } | { ok: false; error: string };
const fail = (error: unknown, fallback: string): { ok: false; error: string } => ({ ok: false, error: error instanceof ApiError ? error.message : fallback });

export type NewItem = {
  kind: "new_page" | "refresh";
  title: string;
  target: string;
  source_area: "gap" | "refresh" | "manual";
  source_key?: string | null;
  due?: string | null;
  assignee_email?: string | null;
  notes?: string | null;
};
export type ItemChange = { title?: string; status?: CalendarStatus; due?: string; clear_due?: boolean; assignee_email?: string; notes?: string };

export async function peopleAction(clientId: string): Promise<R<Person[]>> {
  try {
    return { ok: true, value: await apiFetch<Person[]>("/v2/engine/tasks/people", { clientId }) };
  } catch {
    return { ok: true, value: [] }; // the assignee is optional: an item can be added unassigned
  }
}

export async function calendarAction(clientId: string, dropped = false): Promise<R<CalendarData>> {
  try {
    return { ok: true, value: await apiFetch<CalendarData>(`/v2/content/calendar${dropped ? "?dropped=true" : ""}`, { clientId }) };
  } catch (e) {
    return fail(e, "The calendar could not be read: the API did not answer.");
  }
}

export async function addItemAction(clientId: string, item: NewItem): Promise<R<CalendarItem & { created: boolean }>> {
  try {
    return { ok: true, value: await apiFetch<CalendarItem & { created: boolean }>("/v2/content/calendar", { method: "POST", clientId, body: item }) };
  } catch (e) {
    return fail(e, "That could not be added: the API did not answer.");
  }
}

export async function updateItemAction(clientId: string, id: string, change: ItemChange): Promise<R<CalendarItem>> {
  try {
    return { ok: true, value: await apiFetch<CalendarItem>(`/v2/content/calendar/${id}`, { method: "PATCH", clientId, body: change }) };
  } catch (e) {
    return fail(e, "That could not be saved: the API did not answer.");
  }
}

export async function removeItemAction(clientId: string, id: string): Promise<R<true>> {
  try {
    await apiFetch(`/v2/content/calendar/${id}`, { method: "DELETE", clientId });
    return { ok: true, value: true };
  } catch (e) {
    return fail(e, "That could not be removed: the API did not answer.");
  }
}

export async function sendItemAction(clientId: string, id: string): Promise<R<CalendarItem>> {
  try {
    return { ok: true, value: await apiFetch<CalendarItem>(`/v2/content/calendar/${id}/send`, { method: "POST", clientId }) };
  } catch (e) {
    return fail(e, "It could not be sent to Teamwork: the API did not answer.");
  }
}
