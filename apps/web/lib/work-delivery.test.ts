import assert from "node:assert/strict";
import { runWorkBatch } from "./work-delivery";
async function main() {
  const calls: number[] = [];
  const rows = [0, 1, 2, 3].map((value) => ({
    key: String(value),
    title: `Task ${value}`,
    alreadySent: value === 0,
    value,
  }));
  const result = await runWorkBatch(rows, true, async (value) => {
    calls.push(value);
    if (value === 1) return { ok: false, error: "Provider rejected task" };
    if (value === 2) throw new Error("Connection interrupted");
    return { ok: true };
  });
  assert.deepEqual(calls, [1, 2, 3]); // Never retry a task already known to be delivered.
  assert.deepEqual(result.deliveredKeys, ["0", "3"]);
  assert.deepEqual(
    rows
      .map((row) => row.key)
      .filter((key) => !result.deliveredKeys.includes(key)),
    ["1", "2"],
  );
  assert.match(result.messages[1], /Provider rejected/);
  assert.match(result.messages[2], /Connection interrupted/);
  const assigned = await runWorkBatch(rows.slice(0, 1), false, async () => ({
    ok: true,
  }));
  assert.deepEqual(assigned.deliveredKeys, []); // Assignment never counts as delivery.
  console.log(
    "work-delivery: partial failures, retry selection and duplicate protection passed",
  );
}
main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
