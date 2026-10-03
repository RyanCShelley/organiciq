## Three rules that were written off too early, 2 Oct 2026

Soft 404s, render-critical resources blocked by robots.txt, and the no-CTA
check were all filed as "no data source" because SE Ranking's Website Audit
has no check for any of them. SE Ranking is not the only crawler here. The
first-party crawler fetches the DOM with lxml and already loads and parses
`robots.txt`, which is everything these three needed. The gap was in how far
I looked, not in the data.

- **Soft 404s.** A page returning 200 whose title or H1 says it is missing.
  Google drops these exactly as it drops a real 404. The pattern is narrow
  on purpose: "not found" inside a sentence is ordinary prose, so it only
  matches a title or H1 that is *about* being missing.
- **Render-critical resources.** Scripts and stylesheets a page loads that
  `robots.txt` disallows. Google renders without them and ranks what is
  left. Only resources on the host that `robots.txt` governs are counted — a
  CDN has its own rules we have not read, and guessing would turn every site
  using one into a finding.
- **Nothing to convert through** (N4's first CRO check). No form, phone or
  email link, or call-to-action button, on a page taking at least
  `cta_min_sessions` (30) sessions. Files under Conversion Path, not
  Technical SEO: it is not a defect, it is the conversion path missing from
  a page people already reach.

Migration `0038` adds `soft_404`, `blocked_resources` and
`conversion_elements` to the crawl snapshot. `conversion_elements` is
nullable with no default — a crawl that ran before this check counted
nothing, and recording that as zero would report every page crawled so far
as having no way to convert.

Still open, and genuinely needing a decision rather than more looking: N1's
competitor citations (SE Visible has the data — 6,207 cited sources for SMA,
tagged you/competitors/editorial — but it needs a new ingestion pipeline),
N3 intent mismatch, GA4's device dimension, mobile LCP, and S2's lead-value
field.

## Decision engine review — Phases 3–5, 2 Oct 2026

No migration. `decision_thresholds.thresholds` is JSONB merged with the
defaults at read time, so every new key below already applies to every
existing client and can be overridden per client without a deploy.

### Phase 3 — technical rules

- **Orphan pages with demand are blocking.** A page nothing links to cannot
  be reached by a crawler following links or by a visitor browsing the site,
  however well it ranks. `orphan_min_impressions` (30) is the qualifier:
  most orphans are drafts and thank-you pages.
- **Titles moved to SERP & CTR**, split from meta descriptions, and can now
  be promoted. A title earns the click; a description is upkeep Google
  rewrites at will. They were one signal (`missing_meta` / `duplicate_meta`),
  so the half that moves clicks could never compete for an action. Title is
  checked first, since only one signal is reported per page.
- **Gate 0 gains its two non-silence failures**, neither of which suppresses
  anything: one form going quiet while the site still converts
  (`partial_break_days` 14, `partial_break_min_expected_leads` 3), and leads
  past `lead_spike_multiple` (3×) of the usual rate with at least
  `lead_spike_min_leads` (10) recorded — what double firing and form spam
  look like. Silence makes every score a fiction, which is what earns that
  gate its veto; these make some scores wrong, and the honest answer is to
  say which.

### Phase 4 — new rules, each behind a flag that defaults on

- **N1 AI share of voice falling** (`rule_ai_sov_falling_enabled`). The
  per-prompt rule states a fact about one prompt that stays true for months;
  this asks whether the tracked set is moving. `ai_sov_drop_pct` (20%
  relative) over `ai_sov_window_days` (30), floored at
  `ai_sov_min_presence_pct` (5%) — a 20% relative fall from a 2% share is one
  prompt changing its mind.
- **N2 Link reclamation** (`rule_link_reclamation_enabled`,
  `reclaim_min_refdomains` 1). A 404 nobody links to is housekeeping; a 404
  with referring domains is someone else's link pointing at nothing. A
  redirect that dumps every inbound link on the homepage counts too: the link
  survives, what it was about does not.
- **N4, in part.** AI referrals are reported as their own segment on every
  page finding. AI assistants report no impressions, so the organic numbers
  cannot say whether that surface earns anything.

### Phase 5 — scoring

- **S1 Effort as a size.** Every rule carries S/M/L and the top
  `effort_reorder_top_n` (25) is re-ordered by impact × confidence ÷ weight
  (`effort_weight_small` 1.0, `_medium` 1.5, `_large` 2.5). Only the order
  moves — promotion still turns on impact and confidence, so nothing is
  promoted or blocked for being cheap or expensive. The engine's existing
  per-lever effort of 0–100 priced every Technical SEO finding at 45, title
  rewrite and migration alike. The size shows in the findings table.
- **S3 The impact units, documented in code.** Impact is a percentage of a
  *quarter* of the period goal, not of the goal — the two readings differ by
  a factor of four. On a 20-lead goal an impact of 25 is 1.25 leads, and the
  promotion floor of 25 means "worth at least a sixteenth of the month".
  There is a test asserting exactly that.

### Not built, and why

Each of these was specified in the review and has no data source. Nothing
was stubbed or approximated.

| Item | Why |
|---|---|
| Soft 404s | SE Ranking's Website Audit has no such check. The full code list from SMA's live audit was read before deciding. |
| Render-critical JS/CSS blocked by robots.txt | SE Ranking reports resource *status* errors (`js45xx`, `extjs345xx`, `css45xx`) but nothing for resources disallowed in robots.txt, and only pages are stored, not the resources a page loads. |
| N1's competitor-citation clause | Nothing stores which competitors a prompt cites; the prompt fact holds the client's own `brand_cited` only. "Prompt never cited" therefore stays rather than being replaced — dropping it would have removed 25 findings from SMA and given nothing back. |
| N3 Intent mismatch | No SERP results are stored, with or without page-type classification. |
| N4 "no CTA on the page" | No page body or DOM is stored. |
| N4 mobile vs desktop conversion | GA4 facts carry no device dimension. Adding one is an ingestion change plus a re-sync of every client — a decision, not a detail. |
| N4 mobile LCP | No Core Web Vitals are stored. SE Ranking exposes `chrome_ux_lcp` / `lighthouse_lcp` as boolean issue flags, not milliseconds, and neither is in the curated code list. |
| S2 Lead-value weighting | Conditional on a persona or lead-value field; none exists on the client or on any conversion definition. |

## Decision engine review — Phase 2 (thresholds and rules), 2 Oct 2026

Every number below is a per-client row in `decision_thresholds`, tunable
without a deploy. Full rule set: [docs/decision-engine-rules.md](docs/decision-engine-rules.md).

- **T1** Gate 1's small-sample guard, `gate1_min_expected_leads` (10). A rate
  that moved on four expected leads moved on noise. Each trigger expects
  against the rate it compares to — sharing one rate would have silenced the
  "below baseline" trigger on exactly the chronically under-converting client
  it exists for.
- **T2** Gate 2 reads `gate2_capture_ratio` (0.5) instead of a literal.
- **T3** Gate 3's page-type comparison needs `gate3_page_type_min_pages` (5)
  and `gate3_page_type_min_leads` (10) behind it to be fair.
- **T4** Link floors by what a page is for — `link_floor_money` (10),
  `link_floor_industry` (6), `link_floor_blog` (3) — and donors picked by
  what they have to lend, capped at `link_max_donors` (3).
- **T5** A cluster subject needs `cluster_min_phrase_words` (2); a single
  word is a category, not a topic. `cluster_generic_terms` and
  `cluster_excluded_topics` let a client strike terms out.
- **T6** SERP CTR covers position one, skips pages that are mostly brand
  searches, and uses the client's own CTR curve when the account is big
  enough to fit one (1,000 impressions across 20 pages). A curve fitted to a
  single page judged that page against itself and always found it average.
- **T7** A page whose clicks fell while impressions held within
  `decay_impressions_flat_pct` (10%) is a listing problem and routes to the
  rule that can fix it. Past `light_refresh_min_drop_pct` (20%) it earns a
  deep refresh.
- **T8** Dismissals carry a reason. `wrong_data` and `already_done` no longer
  count against a rule — they are complaints about the input. A contested
  rule gets another chance after `contested_reset_days` (90) or as soon as
  the client's thresholds change.
- **C1** Confidence is read from the evidence (tier, sample size, freshness)
  instead of being a constant per lever, with the lever's constant as the
  ceiling. **Applying it is off by default** (`data_driven_confidence_enabled`),
  because the 60 gate has never rejected a finding and switching this on
  would start rejecting work. The score is recorded on every finding as
  `data_driven_confidence`; `python -m app.confidence_distribution` reads it
  back. See "Confidence, measured" below.
- Fixed: `merge_thresholds` silently dropped list-valued overrides, which
  left T5's two term lists tunable only by deploy.

### Confidence, measured

First run across all clients, 3 Sep – 2 Oct 2026, 222 findings from the four
clients whose data sources are complete:

| Band | Findings |
|---|---|
| 40–49 | 47 |
| 50–54 | 133 |
| 55–59 | 4 |
| 60–69 | 35 |
| 70–79 | 3 |

Median 54. **83% of findings fall below the existing gate of 60**, and 5 of
22 currently-promoted findings would stop being recommended. The gate value
has not been changed: 60 was calibrated against constants that started at 70,
and reusing it against a score that starts lower would reject most of the
engine's output. Decision pending.

### Not built, and why

- **AI Overview multipliers.** `earned_serp_features` records features the
  client *won*, not features present on the SERP — the inverse of the
  question. No data source answers it today.
- **Traffic Potential.** Not available from any connected source.
- **Donor anchor verification.** No page body text is stored, so a donor's
  suggested anchor cannot be checked against what the page actually says.
- **Paid rules.** No ads integration.

## Decision engine review — Phase 1 (logic bugs), 2 Oct 2026

- **B1** Gate 0 no longer suppresses blocking technical findings on pages that
  drew traffic in the previous period. A 5xx on a page with demand is true
  whatever the conversion tag is doing, and suppressing it hid the most urgent
  thing on the site behind the second most urgent.
- **B2** Blocking technical checks read eligibility from the previous period,
  the sitemap, or the page being commercial/conversion — instead of the global
  30-impression demand gate, which hid broken pages by the same mechanism that
  broke them. New threshold `technical_blocking_min_prior_impressions` (30).
- **B3** Not changed. The review's premise did not hold: the data-confidence
  haircut multiplies impact, not confidence, so estimated findings promote
  above roughly 5.5 leads rather than never. Logged as C1 for Phase 2 —
  `finding.confidence` is a per-lever constant of 70–85 and the 60 gate is
  therefore dead code.
- **B4** Impact on one URL is capped at its largest single finding and shared
  between them in proportion. Three rules describing one page's unrealised
  traffic were counted three times. Raw values kept for display.
- **B5** `GATE_BEHAVIOUR` states what each gate suppresses and which bucket it
  routes to. Only Gate 0 suppresses; Gates 1–3 compete on impact.
