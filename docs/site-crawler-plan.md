# First-party site crawler — scope

Written 2026-09-22, against `e297658`.

Replaces SE Ranking's Website Audit as the source of crawl facts, and adds
structured-data extraction, which no current source provides.

The trigger was a false finding on Element Six: `/the-ultimate-guide-…` 301s to
`/the-ultimate-guide-…/`, and SE Ranking's audit returned only the redirecting
variant. Search Console demand for the served page joined onto a crawl row
whose status was 301, and the Technical lever reported "Non-indexable page with
demand" for a site doing the correct thing. `e297658` stops the false alarm.
It does not fix what is underneath: **we have no crawl snapshot of the served
page at all**, so the Technical lever is blind to it rather than wrong about it.

---

## The three questions, answered honestly

### Faster?

For the thing that matters, yes — but not because Scrapy out-runs Screaming
Frog.

SE Ranking's audit is a crawl *they* schedule and we poll. Element Six's most
recent audit finished 2026-09-19; we cannot ask for a fresher one on demand,
and `resolve_project_audit` refuses to run while a crawl is in progress. A
crawl we own runs when we ask and finishes when it finishes.

Raw throughput is not the win, and I would not sell it as one. A 57-page site
is seconds either way. At 35 clients on a monthly cadence, total crawl volume
is roughly one site per day — throughput is nowhere near being the constraint.

### More accurate?

Yes, in three specific ways, and I want to be precise rather than enthusiastic:

1. **We follow redirects and record the destination.** The exact defect above
   disappears, because the page we store is the one that serves a 200.
2. **We control canonical handling.** `normalize_url` strips trailing slashes
   and `_normalize_canonical` does the same, which is why the canonical guard
   could not catch this case — a page whose canonical is its own slashed form
   compares equal to itself. Our own crawler can record the canonical as served,
   before normalization flattens it.
3. **We see every page we choose to see.** SE Ranking decided which variant to
   crawl. We decide.

**On JavaScript — raw HTML is the deliberate lens, not a limitation.**

An earlier draft of this plan treated raw-HTML crawling as a risk to be
mitigated with a rendering check. That was the wrong framing. If a page's
structured data or canonical only exists after JavaScript runs, that is itself
the finding, and one we want to make: it should be surfaced, taken to the
client, and argued for moving server-side.

The strength of that argument varies by consumer, and the finding has to say so
or it will be wrong in front of a client:

- **AI answer engines** — GPTBot, ClaudeBot, PerplexityBot, CCBot and friends
  fetch HTML and do not execute JavaScript. Client-side schema is invisible to
  them, full stop. Given AI visibility is a first-class lever here, this is the
  case that matters most.
- **`rel=canonical`** — Google's own guidance is to serve it in the HTML;
  JS-injected canonicals are unreliable regardless of consumer.
- **Google and JSON-LD** — Googlebot *does* render, and will generally pick up
  JSON-LD injected by JavaScript. So a finding must not claim "Google cannot see
  your schema". The honest wording is that it is absent from the HTML, invisible
  to AI crawlers, and dependent on rendering for everyone else.

What we give up by never rendering: we cannot tell "no schema at all" from
"schema, but client-side only". That changes the *advice*, not the detection —
"you have this, it is just invisible to AI crawlers, move it server-side" is a
far easier conversation than "add schema". Recovering the distinction later
costs one rendered fetch of a sample page per client, and can be added when a
client case needs it. Not a blocker, and not part of the first build.

### Structured data and schema tests?

Yes, and this is the strongest argument for owning the crawler. Nothing we
currently ingest carries it.

Per page, extract and store:

- **JSON-LD** from `<script type="application/ld+json">` — the format that
  matters in practice
- **Microdata** and **RDFa**, recorded so "no schema" cannot be a parser
  artifact
- Per block: `@type`, `@id`, and whether it parses at all

That supports the checks worth having:

- **Missing entirely** — no schema on a page that should carry it
- **Wrong type for the template** — a service page with only `WebPage`, an
  article with no `Article`/`BlogPosting`, a location page with no
  `LocalBusiness`
- **Invalid JSON** — present but unparseable, which is the same as absent to a
  consumer and invisible in every report we have today
- **Missing required properties** for the declared type
- **Organization / sameAs coverage** at site level

This matters beyond classic SEO. Schema is part of how AI answer engines decide
what a page is, and we already track AI visibility as a first-class lever — so
"is this page legible to an answer engine" belongs next to it.

---

## How it fits what already exists

The plumbing is in place, which is most of why this is worth doing in-house.

**Engine: asyncio + `httpx`, not Scrapy.** Scrapy runs a Twisted reactor, and a
reactor can only be started once per process — our worker is a long-lived
polling loop that would invoke the crawler repeatedly, which fights that model
directly. `httpx` is already a dependency and already carries our retry and
timeout conventions. The only new dependency is an HTML/structured-data parser
(`extruct` covers JSON-LD, microdata and RDFa in one, over `lxml`).

- **Job source.** Add `site_crawl` to `_job_handlers()` in
  `app/services/jobs.py`. Deliberately *not* in `daily_sync._PROVIDER_SOURCES` —
  monthly, plus on demand, the same pattern as the two credit-metered sources.
- **Worker.** Runs in the worker service already split out. No new service, no
  new host, no licence.
- **Staging → facts.** Reuse `StagingSerAuditPage` shape into
  `FactCrawlPageSnapshot`. Everything the Technical lever reads already has a
  column: status, canonical, redirect target and count, indexable, title,
  description, word count, inbound internal links, sitemap membership.
- **Findings.** `detect_technical_signal` keeps working unchanged; it reads the
  fact table, not the source.

### Schema needs new storage

`FactCrawlPageSnapshot` has nowhere to put structured data. One new table,
`facts_crawl_page_schema`, one row per page per block:

| column | purpose |
|---|---|
| `client_id`, `normalized_url` | joins to the snapshot |
| `format` | `json_ld` / `microdata` / `rdfa` |
| `schema_type` | `@type`, normalized |
| `raw` | the block as found, JSONB |
| `parse_error` | null when it parsed; the reason when it did not |

Keeping the raw block matters: schema checks will change as we learn what to
look for, and re-crawling 35 sites to answer a new question is the thing we are
trying to get away from.

---

## Crawl budget and cadence

- **Subdomains are in scope.** Confirmed 2026-09-22. Subdomain pages rank and
  can be missing schema — all twelve of Aquaman's uncovered pages live on `rs.`,
  and an exact-host crawl would have hidden every one. The cost is accepted: a
  client with a large unrelated subdomain spends budget on it, bounded by the
  page limit. A name that merely ends with the domain (`notexample.com`, or
  `example.com.evil.test`) is a different site and is not followed.
- **Monthly per client**, staggered — shipped 2026-09-22. Each client's day of
  the 28-day cycle is derived from its id, so the slots are stable and spread
  without any state tracking whose turn it is; 35 clients land on 21 distinct
  days. A crawl older than 42 days is overdue and runs on the next tick
  regardless of its slot, so a worker outage cannot cost a client a whole cycle.
- **Per-client page cap** — shipped 2026-09-22 as `crawl_page_limit`, set in
  Client settings. Default 500, ceiling 5000. The client's value is the ceiling
  and a job may ask for less but not more: verified with a job requesting 5000
  against a client capped at 15, which crawled 15.
- **Politeness**: respect `robots.txt`, concurrency of 2–4 per host, identify
  ourselves in the user agent with a contact URL. We are crawling clients' own
  sites, but they should be able to see who we are in their logs.
- **Stream to staging.** Do not buffer the crawl in memory and write at the end
  — that is the mistake still open in the GSC and GA4 fetchers, and a crawler is
  where it would bite hardest.

---

## What I would not do

- **Screaming Frog on Railway.** The MCP we have is a stdio extension driving
  the desktop app on a Mac; hosting it means writing and owning an HTTP service
  around a headless Java app, with a persistent volume for database storage
  mode. Headless scheduling is a licensed feature and the licence is per user —
  whether it covers unattended server crawling of 35 client sites is a question
  for Screaming Frog in writing, not something to assume. Not worth it when the
  worker can do this directly.
- **Crawl4AI.** Built to extract clean content for LLMs via headless Chromium
  per page. Wrong cost profile and wrong output — we need response headers and
  link graphs, not readable markdown.
- **Turning on every signal a crawler can emit.** A crawler surfaces a great
  deal that is not a problem. We have just spent a session removing one false
  positive; the way to lose trust in the Decision Engine is to add thirty more.
  Start with the signals the levers already consume, plus schema presence. Add
  others only with a client example that would have been caught.

---

## Parallel run — first results

Three clients, both sources, 2026-09-22. First-party crawls capped at 200 pages
for the comparison, which is why SMA shows pages only SE Ranking found.

| Client | SE Ranking | First-party | Shared | Only SE Ranking | Indexability disagreements |
|---|---|---|---|---|---|
| Element Six | 57 | 203 | 46 | 11 | **18** |
| Aquaman Leak Detection | 113 | 146 | 113 | 0 | 0 |
| SMA Marketing | 427 | **467** | 427 | **0** | 1 |

SMA was re-run uncapped on 2026-09-22: 467 pages in 2m26s. The 224 pages that
appeared to be SE Ranking-only in the capped run were the cap, not coverage —
uncapped, the crawl is a superset, with 40 pages SE Ranking never found. That
also sizes the monthly job: the largest client takes about two and a half
minutes, so 35 clients spread over a month is nothing.

Every one of Element Six's 18 is the same defect: SE Ranking crawled a
trailing-slash redirect and recorded a 301 where the page serves 200. Among
them `/contact`, `/blog`, `/what-is-carbon-fiber`,
`/carbon-fiber-design-services`. The other two sites agree completely, which is
the useful half of the result — the crawler is not inventing differences, and
Element Six is genuinely miscrawled rather than merely crawled differently.

The likely reason Element Six is the outlier: its internal links omit trailing
slashes, so SE Ranking's crawler recorded the redirecting form of each URL.

SMA's single disagreement is a definitional difference, not an error on either
side. `/blog/schema.org-vs-...` is a 200 whose robots meta permits indexing, and
whose canonical points at `/blog/schema-org-vs-...` — dot versus hyphen. SE
Ranking folds that into "not indexable". We keep the two apart: the page permits
indexing, and the canonical is its own signal. Checked against the engine, our
row produces `canonical_elsewhere`, which is the more actionable finding — the
page is not broken, it is a duplicate pointing at its original. Folding the two
together is what produced the original Element Six false positive.

### Schema coverage

| Client | Pages carrying schema | Invalid blocks |
|---|---|---|
| SMA Marketing | 464 of 467 | 0 |
| Aquaman | 131 of 146 | 0 |
| Element Six | 31 of 43 | 0 |

SMA's three uncovered pages are all non-indexable, so no indexable page on the
site is missing schema. Aquaman's 12 uncovered pages are all on the `rs.`
landing-page subdomain. Nothing in the stack reported any of this before.

### Fixed by these runs

Aquaman's first diff listed `.kml`, `.svg`, `.png` and `.jpg` URLs as
"indexable pages with no schema" — images filed as content defects. Asset URLs
are now excluded by extension when links are collected, and any 2xx response
that is not HTML is dropped from the page set. That took Aquaman from 185 pages
to 146 and the no-schema list from 23 to 12 real pages.

---

## Open questions

1. ~~Rendering.~~ **Decided 2026-09-22:** crawl raw HTML deliberately;
   JS-dependent schema and canonicals are findings, not crawl failures. See
   above for how the finding must be worded per consumer.
2. **Cutover.** Run both sources in parallel for a cycle and diff, or switch
   outright? Parallel costs nothing extra (the audit is already being fetched)
   and would have caught this bug.
3. ~~Schema expectations per page type.~~ **Answered 2026-09-22.** Three
   checks ship, all firing only for pages the first-party crawl reached so that
   "no structured data" can never mean "not crawled":

   - `invalid_schema` — present but unparseable. Actionable.
   - `missing_schema` — none at all. Advisory.
   - `missing_schema` with `boilerplate_schema_only` — markup present, but every
     type is the wrapper a plugin emits site-wide. Advisory.

   **"Wrong type for the template" was rejected**, and the reason is worth
   keeping. It needs to know what template a page is, and we have no template
   classifier: `PageType` is *intent* (commercial / informational / …) from a URL
   heuristic, and on Aquaman it labels 41 of 43 pages "informational", service
   pages included. Building a schema expectation on that guess compounds two
   uncertainties. It would also need a schema.org subtype map, or every properly
   marked-up blog post reports as missing `Article` because it declares
   `BlogPosting`.

   Inverting the question avoids both problems. Rather than "is the type right",
   ask "is anything here about this page at all" — which needs no classifier and
   no subtype map, because one descriptive type of any kind satisfies it.

   Measured on live crawls: **1 page flagged out of 140** across the three
   clients — Element Six's homepage, carrying `ImageObject, Organization,
   WebPage, WebSite` and nothing saying what the company makes. On the single
   most important URL of a manufacturer whose AI visibility we track.

   `Person` counts as boilerplate: author markup describes the author, not the
   page. It changes nothing on these three sites, where every post also carries
   `BlogPosting`, but it matters on a thinner one.
4. **Retirement.** Does `se_ranking_audit` stay as a cross-check, or go? It
   still supplies issue codes the Technical lever reads.
