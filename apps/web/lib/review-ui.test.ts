import { visibilitySummary } from "./visibility-summary";
import assert from "node:assert/strict";
import { mergeBrief, individualAction, includesProposal, suggestedPlan, actionCount, toggleAction, selectedAction, type Brief } from "./plan-review";
import { metricExplanation } from "./metric-explanation";
import type { BranchTest } from "./monthly-record";

const row = (uid: string, ids: string[], steps: string[]): Brief => ({
  action_uid: uid, id: ids[0], family: "priority_page", title: "Improve page",
  target_url: "https://example.com/service", branch: "visibility", term: "service",
  why: `Reason ${uid}`, done_when: `Done ${uid}`, steps, evidence: [`Evidence ${uid}`],
  finding_ids: ids, effort_min: 30, metric: "Term position", metric_key: "term_position", check_after_days: 28,
});
const original = row("a", ["V-1"], ["Check intent"]);
const incoming = row("b", ["V-3"], ["Check intent", "Validate entity graph"]);
const merged = mergeBrief(original, incoming);
assert.deepEqual(merged.steps, ["Check intent", "Validate entity graph"]);
assert.match(merged.why, /Reason a[\s\S]*Reason b/);
assert.match(merged.done_when, /Done a[\s\S]*Done b/);
assert.equal(merged.action_uid, original.action_uid);
assert.equal(includesProposal(merged, incoming), true);
assert.deepEqual(mergeBrief(merged, incoming), merged); // repeat clicks cannot duplicate work
assert.deepEqual(original.steps, ["Check intent"]); // saved state stays untouched
assert.equal(suggestedPlan([original, incoming, { ...row("c", ["V-4"], ["Link"]), target_url: "https://example.com/other" }], "visibility", 5).length, 3);
assert.equal(suggestedPlan([original, incoming], "visibility", 1).length, 1);

const explanation = (id: string, value: number, evidence: Record<string, number>) => metricExplanation({ id, value, evidence } as BranchTest).calculation;
assert.match(explanation("V1", 25, { in_top_10: 2, priority_keywords: 8 }), /2.*8.*25%/);
assert.match(explanation("T1", 75, { estimated_missed_clicks: 150, actual_clicks: 50, formula_version: 2 }), /150.*150.*50.*75%/);
assert.match(explanation("L1", 2, { lead_rate_pct: 2, target_rate_pct: 3, formula_version: 2 }), /2%.*3%/);
assert.match(metricExplanation({ id: "T1", value: 300 } as BranchTest).calculation, /Superseded/);
assert.match(explanation("L1", 3.13, { lead_rate_pct: 3.13, target_rate_pct: 4, formula_version: 3 }), /Visit-based.*3.13%.*4%/);
assert.match(metricExplanation({ id: "L1", name: "Lead conversion", metric_label: "Lead conversion rate", value: 3.13, pass_line: 4, direction: "min", unit: "pct", status: "fail", evidence: { formula_version: 3 } }).limitation, /Each visit counts once/);
console.log("review-ui: merge, inclusion, suggested selection and calculation explanations passed");

const bundled = { ...original, steps: ["Task one", "Task two", "Task three"] };
assert.equal(actionCount([bundled, { ...incoming, steps: ["Task four", "Task five"] }]), 5);
let choices = toggleAction([], bundled, "Task two", 1);
assert.equal(actionCount(choices), 1);
assert.equal(choices[0].done_when, "Task two");
assert.equal(selectedAction(choices, bundled, "Task two")?.action_uid, choices[0].action_uid);
choices = toggleAction(choices, bundled, "Task two", 1);
assert.equal(choices.length, 0);
const unbundled = toggleAction([bundled], bundled, "Task two", 1);
assert.deepEqual(unbundled.map(x => x.steps), [["Task one"], ["Task three"]]);
assert.equal(new Set(unbundled.map(x => x.action_uid)).size, 2);
const normalized = toggleAction([bundled, { ...incoming, steps: ["Task four", "Task five"] }], bundled, "Task two", 1);
assert.equal(normalized.length, 4);
assert.ok(normalized.every(item => item.steps.length === 1));
assert.equal(actionCount(normalized), 4);
const locked = toggleAction([bundled], bundled, "Task two", 1, [bundled.action_uid]);
assert.deepEqual(locked, [bundled]);


const trackedTerms = Array.from({length: 20}, (_, i) => ({ text: `term ${i}`, priority: false, position: i === 0 ? 1 : null, status: i === 0 ? "top_10" : "not_in_top_100", target_url: null, ranking_url: null }));
assert.equal(visibilitySummary(trackedTerms).value, "1 of 20");
assert.equal(visibilitySummary(trackedTerms).note, null);
assert.equal(visibilitySummary(trackedTerms.map((term, index) => ({...term, priority: index === 0}))).value, "1 of 20");
assert.equal(visibilitySummary([]).value, "No tracked keywords");
assert.equal(visibilitySummary([{...trackedTerms[0], status:"not_measured", position:null}]).value, "No dated rankings");

// Current setup explains old run limits without silently rewriting saved evidence.
import { dataGapGuidance } from "./data-gap-guidance";
const configured = {target_lead_rate_pct: 2, conversion_page_count: 1};
assert.match(dataGapGuidance("no target lead conversion rate", configured).title, /2%/);
assert.match(dataGapGuidance("no target or conversion pages declared", configured).title, /configured now/);
assert.match(dataGapGuidance("no target lead conversion rate", {target_lead_rate_pct: null, conversion_page_count:0}).title, /Set the target/);
assert.match(dataGapGuidance("no keyword group is marked priority").next, /No separate priority/);
assert.match(dataGapGuidance("CTR reference is diagnostic only").next, /does not require an observed AI Overview/);

import {resolveQueryRange} from "./date-range";
assert.deepEqual(resolveQueryRange(undefined, "2026-09-01", "2026-09-30"), {from:"2026-09-01",to:"2026-09-30"});
assert.deepEqual(resolveQueryRange("custom", "2026-09-01", "2026-09-30"), {from:"2026-09-01",to:"2026-09-30"});

{
  const base = { action_uid: "group", id: "T-1", family: "priority_page", title: "Page work", branch: "traffic", target_url: "https://example.com/", term: null, why: "Evidence", done_when: "Done", steps: ["Title", "Opening"], evidence: [], finding_ids: [], effort_min: 60, metric: "Clicks", metric_key: "page_clicks", check_after_days: 28 } as Brief;
  const opening = { ...base, action_uid: "opening", id: "T-3", steps: ["Opening"], metric_key: "engagement_rate", metric: "Engagement" };
  const selected = individualAction({ ...base, interventions: [opening] }, "Opening", 1);
  assert.equal(selected.action_uid, "opening");
  assert.equal(selected.metric_key, "engagement_rate");
}
