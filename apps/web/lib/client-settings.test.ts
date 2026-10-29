import assert from "node:assert/strict";
import { isSettingsSection, settingsPatch } from "./client-settings";
import { setupProgress, pageIdentity } from "./client-setup";
import { syncSelectedProperty } from "./setup-sync";
const complete = { done: 9, total: 9, next: null, steps: ["account", "sources", "pull", "leads", "baseline", "conversion_pages", "page_stages", "keyword_targets", "first_run"].map(key => ({ key, title: key, detail: "", done: true, blocked_by: null, link: "" })) };
assert.equal(setupProgress(complete).complete, true);
const newClient = { ...complete, steps: complete.steps.map(s => ({ ...s, done: s.key === "account" })) };
assert.equal(setupProgress(newClient).next, 1);
assert.equal(setupProgress(newClient).complete, false);
const deletedMapping = { ...complete, steps: complete.steps.map(s => ({ ...s, done: s.key !== "keyword_targets" })) };
assert.equal(setupProgress(deletedMapping).next, 4);
const laterBaseline = { ...complete, steps: complete.steps.map(s => ({ ...s, done: s.key !== "baseline" })) };
assert.equal(setupProgress(laterBaseline).complete, true);
assert.equal(isSettingsSection("__proto__"), false);
assert.deepEqual(settingsPatch({ client_name: "Aquaman", monthly_lead_goal: null, competitor_domains: [], teamwork_tasklist_id: null, crawl_page_limit: null, lead_goal_overrides: {} }, "general"), { client_name: "Aquaman" });
assert.deepEqual(settingsPatch({ monthly_lead_goal: 55, lead_goal_overrides: { "12": 55 }, client_name: "", tier_id: "", baseline_monthly_sessions: null }, "goals"), { monthly_lead_goal: 55, lead_goal_overrides: { "12": 55 } });
assert.deepEqual(settingsPatch({ competitor_domains: [], teamwork_tasklist_id: "123", service_reporting: null }, "connections"), { teamwork_tasklist_id: "123" });
assert.equal(pageIdentity("https://www.example.com/contact/"), pageIdentity("http://example.com/contact"));
assert.notEqual(pageIdentity("https://a.com/contact"), pageIdentity("https://b.com/contact"));
assert.notEqual(pageIdentity("https://example.com/section/contact"), pageIdentity("https://example.com/contact"));
async function verifySync() {
  const original = globalThis.fetch; const calls: Record<string, unknown>[] = [];
  try {
    globalThis.fetch = async (_url, init) => { const body = JSON.parse(String(init?.body)); calls.push(body); return new Response("", { status: body.source === "gsc_pages" ? 409 : 200 }); };
    assert.equal(await syncSelectedProperty("pilot", ["gsc_pages", "gsc_queries"]), null);
    assert.equal(calls.length, 2); assert.ok(calls.every(c => c.clientId === "pilot"));
    assert.ok(calls.every(c => c.start_date && c.end_date));
    globalThis.fetch = async () => new Response("failed", { status: 503 });
    assert.match((await syncSelectedProperty("pilot", ["ga4"]))!, /Property saved.*could not start/);
    globalThis.fetch = async () => { throw new Error("offline"); };
    assert.match((await syncSelectedProperty("pilot", ["ga4"]))!, /Retry/);
  } finally { globalThis.fetch = original; }
}
verifySync().then(() => console.log("client-settings: field isolation, saved readiness, page identity and sync retry checks passed"));
