// Run with: npx tsx apps/web/lib/client-path.test.ts
import assert from "node:assert/strict";

import { ACCOUNT_TOOLS } from "./account-routes";
import { withNavContext, navigationClient } from "./navigation";
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
  const href = withNavContext(
    `/aquaman-leak-detection/${tool}`,
    "pilot-id",
    "2026-09-01",
    "2026-09-30",
  );
  const url = new URL(href, "https://www.organiciq.app");
  assert.equal(url.searchParams.get("range"), "custom");
  assert.equal(url.searchParams.has("clientId"), false);
  const range = resolveQueryRange(
    url.searchParams.get("range")!,
    url.searchParams.get("from")!,
    url.searchParams.get("to")!,
  );
  assert.equal(range.from, "2026-09-01");
  assert.equal(range.to, "2026-09-30");
}

// Client URL context must survive a platform detour despite a stale layout cookie.
const pilots = [
  { id: "aquaman-id", slug: "aquaman" },
  { id: "sma-id", slug: "sma" },
  { id: "acctek-id", slug: "acctek" },
];
assert.equal(
  navigationClient(pilots, "/aquaman/dashboard", "sma-id", "acctek-id")?.id,
  "aquaman-id",
);
assert.equal(
  navigationClient(pilots, "/clients/aquaman/jobs", null, "acctek-id")?.id,
  "aquaman-id",
);
assert.equal(
  navigationClient(pilots, "/platform/jobs", "aquaman-id", "acctek-id")?.id,
  "aquaman-id",
);
assert.equal(
  navigationClient(pilots, "/platform/data-health", "unknown-id", "acctek-id")
    ?.id,
  "acctek-id",
);
assert.equal(
  navigationClient(pilots, "/clients", null, "sma-id")?.id,
  "sma-id",
);
assert.equal(
  navigationClient(pilots, "/platform", "unknown-id", "unknown-id"),
  undefined,
);
const platformDetour = withNavContext(
  "/platform/jobs",
  "aquaman-id",
  "2026-09-01",
  "2026-09-30",
);
const context = new URL(platformDetour, "https://www.organiciq.app")
  .searchParams;
const returningClient = navigationClient(
  pilots,
  "/platform/jobs",
  context.get("clientId"),
  "acctek-id",
);
assert.equal(returningClient?.slug, "aquaman");
assert.equal(
  withNavContext(
    `/${returningClient!.slug}/dashboard`,
    returningClient!.id,
    context.get("from")!,
    context.get("to")!,
  ),
  "/aquaman/dashboard?from=2026-09-01&to=2026-09-30&range=custom",
);
