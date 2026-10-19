// Run with: npx tsx apps/web/lib/client-path.test.ts
import assert from "node:assert/strict";

import { ACCOUNT_TOOLS } from "./account-routes";
import { withNavContext } from "./navigation";
import { resolveQueryRange } from "./date-range";
import { clientHref } from "./client-path";

// Settings pages live under /clients/{slug}.
assert.equal(clientHref("acme"), "/clients/acme");
assert.equal(clientHref("acme", "integrations"), "/clients/acme/integrations");

// Product tools live at /{slug}/{tool}. /clients/{slug}/dashboard has never
// been a route, and every sortable dashboard header linked to it.
for (const tool of ACCOUNT_TOOLS) {
  assert.equal(clientHref("acme", tool), `/acme/${tool}`, tool);
}

console.log("client-path: ok");

// The monthly review must keep explicit September dates when crossing pages.
for (const tool of ["dashboard", "decision-engine", "annotations"]) {
  const href = withNavContext(`/aquaman-leak-detection/${tool}`, "pilot-id", "2026-09-01", "2026-09-30");
  const url = new URL(href, "https://www.organiciq.app");
  assert.equal(url.searchParams.get("range"), "custom");
  assert.equal(url.searchParams.has("clientId"), false);
  const range = resolveQueryRange(url.searchParams.get("range")!, url.searchParams.get("from")!, url.searchParams.get("to")!);
  assert.equal(range.from, "2026-09-01"); assert.equal(range.to, "2026-09-30");
}
