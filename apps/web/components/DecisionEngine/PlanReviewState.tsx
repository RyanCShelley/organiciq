"use client";
import { createContext, useContext, useState, type ReactNode } from "react";

const PlanState = createContext({ dirty: false, setDirty: (_value: boolean) => {} });
export const usePlanState = () => useContext(PlanState);

export function PlanReviewState({ children }: { children: ReactNode }) {
  const [dirty, setDirty] = useState(false);
  return <PlanState.Provider value={{ dirty, setDirty }}>{children}</PlanState.Provider>;
}

export function ApprovedWork({ children }: { children: ReactNode }) {
  const { dirty } = usePlanState();
  if (dirty) return <p role="status" className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-4 text-sm">Your selection has changed. Approve the revised actions before assigning or sending them to Teamwork.</p>;
  return children;
}
