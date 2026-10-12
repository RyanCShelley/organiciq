// Run with: npx tsx apps/web/components/DecisionEngine/keyword-map.test.ts
import assert from "node:assert/strict";

// Mirrors the helpers in KeywordPageMapTable: every row points at the same
// domain, so showing it in every field spends two dozen characters on the
// one thing never in question and truncates the part that is.
function siteOrigin(pages: string[]): string | null {
  for (const page of pages) {
    try {
      return new URL(page).origin;
    } catch {
      continue;
    }
  }
  return null;
}
function forDisplay(url: string, origin: string | null): string {
  if (!origin || !url.startsWith(`${origin}/`)) return url;
  return url.slice(origin.length) || "/";
}
function forSaving(value: string, origin: string | null): string {
  const text = value.trim();
  if (!origin || !text.startsWith("/")) return text;
  return `${origin}${text}`;
}

const origin = siteOrigin(["https://smamarketing.com/capabilities/seo"]);
assert.equal(origin, "https://smamarketing.com");

// Half a dozen capabilities pages all read the same until the domain goes.
assert.equal(
  forDisplay("https://smamarketing.com/capabilities/local-seo", origin),
  "/capabilities/local-seo",
);
assert.equal(forDisplay("https://smamarketing.com/", origin), "/");

// Another domain keeps its whole URL: the path alone would be a lie.
assert.equal(
  forDisplay("https://partner.example.com/x", origin),
  "https://partner.example.com/x",
);

// What is shown round-trips to what is stored.
for (const url of [
  "https://smamarketing.com/capabilities/seo",
  "https://smamarketing.com/",
  "https://partner.example.com/x",
]) {
  assert.equal(forSaving(forDisplay(url, origin), origin), url, url);
}

// A path typed by hand belongs to this site.
assert.equal(
  forSaving("/industries/contractors", origin),
  "https://smamarketing.com/industries/contractors",
);
// Emptiness stays empty rather than becoming the homepage.
assert.equal(forSaving("", origin), "");
// With no crawl to learn the origin from, nothing is invented.
assert.equal(forSaving("/a", null), "/a");
assert.equal(forDisplay("https://x.test/a", null), "https://x.test/a");

console.log("keyword-map: all assertions passed");
