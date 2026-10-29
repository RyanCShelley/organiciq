import assert from "node:assert/strict";

import { effectivePlan, type Candidate } from "./monthly-record";

function row(uid: string, slot: number | null, score: number): Candidate {
  return { action_uid: uid, slot, score, not_slotted_because: null } as unknown as Candidate;
}

const candidates = [row("a", 1, 90), row("b", 2, 80), row("c", null, 70), row("d", null, 60)];
const state = (overrides: Record<string, boolean | null>) =>
  new Map(Object.entries(overrides).map(([uid, in_plan]) => [uid, { in_plan }]));

// No override: the engine's plan, untouched.
{
  const plan = effectivePlan(candidates, state({}));
  assert.deepEqual(plan.planned.map((r) => r.action_uid), ["a", "b"]);
  assert.deepEqual(plan.left.map((r) => r.action_uid), ["c", "d"]);
  assert.equal(plan.added, 0);
  assert.equal(plan.removed, 0);
}

// Swap: take b out, put d in. The pick joins after the engine's kept slots and
// slots are renumbered in display order.
{
  const plan = effectivePlan(candidates, state({ b: false, d: true }));
  assert.deepEqual(plan.planned.map((r) => [r.action_uid, r.slot]), [["a", 1], ["d", 2]]);
  // Best first, so the one just taken out (80) sits above the one never chosen (70).
  assert.deepEqual(plan.left.map((r) => r.action_uid), ["b", "c"]);
  assert.equal(plan.added, 1);
  assert.equal(plan.removed, 1);
}

// More picks than the allowance is allowed: the team has the last word.
{
  const plan = effectivePlan(candidates, state({ c: true, d: true }));
  assert.deepEqual(plan.planned.map((r) => r.action_uid), ["a", "b", "c", "d"]);
}

// null hands the decision back to the engine.
{
  const plan = effectivePlan(candidates, state({ b: null, c: null }));
  assert.deepEqual(plan.planned.map((r) => r.action_uid), ["a", "b"]);
}

console.log("effective-plan: ok");
