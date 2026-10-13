// Run with: npx tsx apps/web/lib/client-path.test.ts
import assert from "node:assert/strict";

import { ACCOUNT_TOOLS } from "./account-routes";
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
