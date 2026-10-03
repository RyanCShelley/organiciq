# Decision Engine — the rules, as they run

Every rule below is in `apps/api/app/services/lever_engine.py` and proven by a
test. Thresholds in **bold** are per-client rows in `decision_thresholds`,
tunable without a deploy; the number given is the default.

The engine answers business questions in order — **leads, then traffic, then
visibility** — because visibility earns traffic and traffic earns leads.
A finding about leads outranks one about rankings however the two score.

Each finding says what is wrong *and* prescribes the action to take.

---

## The cascade

| | Question | Bucket | Suppresses |
|---|---|---|---|
| **Gate 0** | Are conversions being recorded at all? | Conversion Path | Everything except blocking technical findings on pages that had traffic last period |
| **Gate 0** | Has one form gone quiet while the site still converts? | Conversion Path | Nothing |
| **Gate 0** | Are leads far above the usual rate? | Conversion Path | Nothing |
| **Gate 1** | Is the site converting at the level the plan requires? | Conversion Path | Nothing |
| **Gate 2** | Do core terms rank and bring nothing? | Search & AI Visibility | Nothing |
| **Gate 3** | Do pages earn traffic and turn it into nothing? | Conversion Path | Nothing |

Only Gate 0 suppresses. Gates 1–3 compete on impact. The table is generated
from `GATE_BEHAVIOUR`, so a gate that changes its mind shows up here.

**Gate 0's exception exists because a 5xx on a page with demand is true
whatever the conversion tag is doing.** Suppressing it hid the most urgent
thing on the site behind the second most urgent.

---

## Gate 0 — Tracking

Fires when traffic holds and recorded conversions collapse to nothing. That
shape is a broken tag far more often than a dead month.

**Action:** verify the conversion event is still firing before trusting any
other number on the page.

Two more Gate 0 checks fire on a site that is still converting, and neither
suppresses anything — silence makes every score a fiction, which is what
earns that gate its veto; these make *some* scores wrong, and the honest
answer is to say which.

**Partial break.** One page stops producing conversions for
**`partial_break_days`** (14) while the rest of the site carries on. The
site total hides this completely. Guarded by
**`partial_break_min_expected_leads`** (3), measured against that page's own
prior rate.

**Spike.** Leads past **`lead_spike_multiple`** (3×) the usual rate with at
least **`lead_spike_min_leads`** (10) recorded — what double firing and form
spam look like. Its impact is the excess over the expected rate: the
recorded leads that may not exist.

## Gate 1 — Site conversion

Three triggers, each compared against the rate it is actually claiming to
beat:

- the lead rate fell by more than **`conversion_lead_rate_decline_min_pct`**
  (10%) against the previous period;
- sessions grew more than **`conversion_sessions_growth_min_pct`** (5%) while
  leads did not follow;
- the rate sits below the client's own baseline.

Each trigger is guarded by **`gate1_min_expected_leads`** (10): a rate that
moved on four expected leads moved on noise. The guard expects against the
rate each trigger compares to, not a single shared rate — otherwise the
"below baseline" trigger would go silent on exactly the chronically
under-converting client it exists for.

## Gate 2 — Visibility without traffic

Core terms ranking and earning nothing. Clicks below
**`gate2_capture_ratio`** (0.5) of what the position should earn.

## Gate 3 — Conversion pages

Pages drawing traffic that converts below their own page type. A page type
needs **`gate3_page_type_min_pages`** (5) and **`gate3_page_type_min_leads`**
(10) behind it to be a fair comparison.

---

## Growth-action rules

### SERP & CTR
Position 1–10, at least 1,000 impressions, CTR under half the curve's
expected rate (`UNDERPERFORMANCE_RATIO`, 0.5) with at least 5 clicks
recoverable (`MIN_RECOVERABLE_CLICKS`). Both are module constants, not
per-client rows. Position one is included — a page ranking first and under-clicked is the cheapest fix on the site, and an
AI Overview above it disproves the idea that first place cannot
under-perform. Pages where branded queries are more than half the impressions
(`BRANDED_SHARE_MAX`) are excluded: brand searches convert at their own rate
and are not a listing problem. The curve is the client's own when the account
has at least 1,000 impressions across 20 pages, otherwise a shared one — a
curve fitted to one page would judge that page against itself.

### Internal linking
Inbound editorial links expected by what the page is for:
**`link_floor_money`** (10), **`link_floor_industry`** (6),
**`link_floor_blog`** (3). Donors are picked by what they have to lend, up to
**`link_max_donors`** (3).

### Content clusters
Subjects the site draws demand for with no page ranking on them. A subject
needs at least **`cluster_min_phrase_words`** (2) words — a single word is a
category, not a topic. **`cluster_generic_terms`** and
**`cluster_excluded_topics`** let a client strike terms out.

### Decay and refresh
Pages that used to perform and no longer do. Clicks down with impressions
flat within **`decay_impressions_flat_pct`** (10%) is a listing problem, not
a demand problem, and routes to the rule that can fix it. A drop past
**`light_refresh_min_drop_pct`** (20%) earns a deep refresh rather than a
light one.

### PR pushes
Pages that earned referring domains recently and no traffic with them — the
link landed and the page did not convert the attention.

### Orphan pages
A page with **`orphan_min_impressions`** (30) impressions and nothing linking
to it. Blocking: it cannot be reached by a crawler following links or by a
visitor browsing the site, however well it ranks. Demand is the qualifier —
most orphans are drafts and thank-you pages.

### Link reclamation
A URL returning 4xx, or redirecting to the homepage, with at least
**`reclaim_min_refdomains`** (1) referring domains. Someone else's link is
pointing at nothing, and the authority stops at the error. A redirect to the
homepage keeps the link and throws away what it was about. Flag:
`rule_link_reclamation_enabled`.

### AI share of voice
The share of tracked prompts mentioning the brand, falling by
**`ai_sov_drop_pct`** (20% relative) over **`ai_sov_window_days`** (30).
Floored at **`ai_sov_min_presence_pct`** (5%): a 20% relative fall from a 2%
share is one prompt changing its mind. Flag:
`rule_ai_sov_falling_enabled`.

### Soft 404s
A page returning 200 whose title or H1 says it is missing. Google drops
these exactly as it drops a real 404, and nothing in the status code shows
it. Detected by the first-party crawler; SE Ranking's audit has no such
check.

### Render-critical resources
Scripts and stylesheets a page loads that `robots.txt` disallows. Google
renders the page without them and ranks what is left, which is not the page
a visitor sees. Only resources on the host that `robots.txt` governs are
counted — a CDN has its own rules and we have not read them.

### Nothing to convert through
No form, phone link, email link or call-to-action button on a page taking at
least **`cta_min_sessions`** (30) sessions. A null count means the crawl
predates the check, which is not the same as counting zero.

### Technical
Titles are **not** here — a missing or duplicate title is SERP & CTR work
that can be promoted, because the title earns the click. Meta descriptions
stay core work; Google rewrites them at will.

Blocking signals (5xx, noindex, canonical conflicts, robots blocks) on pages
with demand. Eligibility reads the previous period, the sitemap, or the page
being commercial/conversion, rather than the global demand gate — which hid
broken pages by the same mechanism that broke them. Minimum prior demand:
**`technical_blocking_min_prior_impressions`** (30).

Technical findings are **core work**: monthly upkeep already in the plan.
They are shown and do not spend a growth action.

---

## Scoring

One currency: leads.

`normalize_business_impact` converts every finding to a share of the client's
period goal — leads ÷ (25% of the period goal) — then applies a haircut for
how the number was arrived at (measured 1.0, inferred 0.85, estimated 0.55).

Impact on one URL is capped at its largest single finding and shared between
them in proportion. Three rules describing one page's unrealised traffic were
being counted three times.

**What an impact number means.** Impact is a percentage of a *quarter* of
the period goal, not of the goal — the two readings differ by a factor of
four. On a 20-lead goal an impact of 25 is **1.25 leads**, and the promotion
floor of 25 means "worth at least a sixteenth of the month".

### Effort

Every rule carries a size — S, M or L — and the top
**`effort_reorder_top_n`** (25) is ordered by impact × confidence ÷ weight
(**`effort_weight_small`** 1.0, **`effort_weight_medium`** 1.5,
**`effort_weight_large`** 2.5).

Only the order moves. Promotion still turns on impact and confidence, so
nothing is promoted or blocked for being cheap or expensive — between two
findings worth the same, the cheaper one simply comes first.

A finding is promoted to a recommendation when impact clears
**`minimum_actionable_impact`** (25) and confidence clears
**`minimum_recommendation_confidence`** (60).

### Confidence (C1)

Confidence used to be a constant per lever (70–85), so it described the kind
of rule rather than the evidence — and since every constant sat above 60, the
confidence gate had never rejected anything.

It is now read from the evidence, with the lever's constant as the ceiling:

- **tier** — `confidence_tier_high` (1.0), `confidence_tier_medium` (0.9),
  `confidence_tier_low` (0.75);
- **sample** — `confidence_small_sample_factor` (0.8) when the finding rests
  on fewer than `confidence_min_sample_leads` (3) expected leads, or fewer
  than `confidence_min_sample_impressions` (100) where no lead estimate was
  made;
- **freshness** — `confidence_stale_factor` (0.85) past
  `confidence_stale_after_days` (14).

**Applying it is off by default** (`data_driven_confidence_enabled`). Turning
it on under an unchanged gate silently stops promoting work. The score is
recorded on every finding either way, as `data_driven_confidence` in the
evidence, and `python -m app.confidence_distribution` reads it back.

---

## When a rule is wrong

A rule dismissed **3** times across different pages (`OVERRIDE_RETIREMENT_COUNT`)
is contested: the rule is the thing that is wrong, not the team. Counting is
by rule *family*, not by `rule_key`, which is hashed per page.

Dismissals carry a reason. `wrong_data` and `already_done` do not count
against a rule — they are complaints about the input, not the rule.

A contested rule gets another chance after **`contested_reset_days`** (90),
or as soon as the client's thresholds change: the rule that was dismissed is
not the rule running now.
