# Decision Engine — every rule, as it runs

Generated against the code, not from memory. Every rule lives in
`apps/api/app/services/lever_engine.py` and is covered by tests. Names in
`code font` are per-client rows in `decision_thresholds`, tunable without a
deploy; the number shown is the default.

**The order is leads, then traffic, then visibility** — visibility earns
traffic and traffic earns leads, so a finding about leads outranks one about
rankings however the two score.

Every rule prescribes an action, not just a diagnosis.

---

## The gates

| | Question | Bucket | Suppresses |
|---|---|---|---|
| **Gate 0** | Are conversions recorded at all? | Leads | Everything except blocking technical findings on pages with traffic last period |
| **Gate 0a** | Has one page stopped converting while the site hasn't? | Leads | Nothing |
| **Gate 0b** | Are leads far above the usual rate? | Leads | Nothing |
| **Gate 1** | Is the site converting at the level the plan needs? | Leads | Nothing |
| **Gate 2** | Do core terms rank and bring nothing? | Visibility | Nothing |
| **Gate 3** | Do pages earn traffic and convert nothing? | Leads | Nothing |

Only total silence has a veto. It makes every score below it a fiction; the
others make *some* scores wrong, and the honest response is to say which.

---

## Leads

| Rule | Fires when | Will not fire when |
|---|---|---|
| **Tracking silent** | No conversions in 14 days while sessions arrive | Nothing configured; under 3 leads expected; no history and under 500 sessions |
| **Partial break** | One page stops converting for `partial_break_days` (14) while the site still does | Under `partial_break_min_expected_leads` (3) expected from that page |
| **Lead spike** | Leads past `lead_spike_multiple` (3×) the usual rate | Under `lead_spike_min_leads` (10) recorded. Impact is the excess — the leads that may not exist |
| **Site conversion** | Rate fell `conversion_lead_rate_decline_min_pct` (10%), or sessions grew `conversion_sessions_growth_min_pct` (5%) without leads, or rate is under the client's baseline | Under `gate1_min_expected_leads` (10) expected, measured against the rate each trigger compares to |
| **Conversion page** | A page converts below its own page type | Page type has under `gate3_page_type_min_pages` (5) pages or `gate3_page_type_min_leads` (10) leads behind it |
| **No conversion element** | No form, phone/email link or CTA button, on a page with `cta_min_sessions` (30)+ sessions | The crawl predates the check (null, not zero) |

## Traffic

| Rule | Fires when | Will not fire when |
|---|---|---|
| **SERP CTR** | Position 1–10, 1,000+ impressions, CTR under half the expected curve, 5+ clicks recoverable | Brand is over half the impressions. Uses the client's own curve only at 1,000+ impressions across 20+ pages |
| **Decaying page** | Clicks fell while impressions held within `decay_impressions_flat_pct` (10%) — a listing problem, routed to the rule that fixes it | — |
| **Deep refresh** | Drop past `light_refresh_min_drop_pct` (20%) | — |
| **PR push unconverted** | A page earned referring domains recently and no traffic with them | A single link is not a push; links over a year old are the status quo |
| **Visibility without traffic** | Core terms rank and earn under `gate2_capture_ratio` (0.5) of what the position should | — |

## Visibility

| Rule | Fires when | Will not fire when |
|---|---|---|
| **Internal linking** | Editorial inbound links under the floor — `link_floor_money` (10), `link_floor_industry` (6), `link_floor_blog` (3) — at position 4–20 | **The homepage, ever.** Donors capped at `link_max_donors` (3) |
| **Content cluster** | The site draws demand for a subject with no page ranking on it | Subjects under `cluster_min_phrase_words` (2) words; anything in `cluster_generic_terms` or `cluster_excluded_topics` |
| **Keyword not ranking** | A tracked keyword has nothing ranking | Volume under `ai_visibility_min_keyword_volume` (50); top `ai_visibility_keyword_top_n` (25) only |
| **Prompt not cited** | A tracked AI prompt never cites the brand | Under `ai_visibility_prompt_min_checks` (2) checks |
| **AI share of voice falling** | Brand mentions across tracked prompts fell `ai_sov_drop_pct` (20% relative) over `ai_sov_window_days` (30) | Starting share under `ai_sov_min_presence_pct` (5%) — a 20% fall from 2% is one prompt changing its mind. Flag: `rule_ai_sov_falling_enabled` |

## Technical

Blocking signals compete for a growth action. Everything else is core work:
reported, never spending one of the client's flexible actions.

| Rule | Blocking | Fires when | Will not fire when |
|---|---|---|---|
| **Status error** | ✓ | 4xx/5xx with demand | — |
| **Soft 404** | ✓ | 200 whose title or H1 says the page is missing | "Not found" inside ordinary prose |
| **Non-indexable** | ✓ | noindex with demand | A working redirect |
| **Canonical elsewhere** | ✓ | The canonical target is **off-site, missing, erroring, or itself non-indexable** | **A canonical pointing at a live page on the same site.** That is correct consolidation, not a defect |
| **Orphan page** | ✓ | No inbound internal links, `orphan_min_impressions` (30)+ impressions | A page nobody searches for |
| **Blocked resources** | ✓ | Scripts/stylesheets robots.txt disallows | Resources on another host — a CDN has its own rules |
| **Broken redirect / chain** | ✓ | Redirect to an error, or 3+ hops | — |
| **Link reclamation** | ✓ | 4xx, or a redirect to the homepage, with `reclaim_min_refdomains` (1)+ referring domains | Flag: `rule_link_reclamation_enabled` |
| **Title missing / duplicate** | — | Filed under **SERP & CTR**, promotable — a title earns the click | — |
| **Description missing / duplicate** | — | Core work. Google rewrites them at will | — |
| **Missing / invalid schema** | — | Core work, only on pages the first-party crawl reached | Boilerplate-only markup is called out separately |
| **Sitemap / robots site-level** | — | Core work | — |

---

## Scoring

One currency: **leads**.

```
reference_leads = 0.25 × period lead goal
impact          = (leads ÷ reference_leads) × 100,  capped at 100
```

So **impact 25 on a 20-lead goal is 1.25 leads** — a sixteenth of the month,
not a quarter. Estimates are discounted by how they were arrived at
(measured 1.0, inferred 0.85, estimated 0.55). Impact on one URL is capped
at its largest single finding and shared in proportion, so three rules
describing one page are not counted three times.

**Promotion** needs impact ≥ `minimum_actionable_impact` (25) and confidence
≥ `minimum_recommendation_confidence` (50).

A critical technical fault clears a lower bar, `critical_override_min_impact`
(5) — lower, not absent. A broken page with nothing behind it is still a page
with nothing behind it.

**Effort** sizes every rule S/M/L and re-orders the top
`effort_reorder_top_n` (25) by impact × confidence ÷ weight
(`effort_weight_small` 1.0, `_medium` 1.5, `_large` 2.5). Order only —
nothing is promoted or blocked for being cheap or expensive.

**Confidence** is measured from the evidence (tier, sample size, freshness),
capped by the lever's own constant. Applying it is behind
`data_driven_confidence_enabled`, currently **off**; the score is recorded on
every finding regardless.

## When a rule is wrong

Dismissed 3 times across different pages and the rule is contested — the
rule is wrong, not the team. Counted by rule family, not by page.
`wrong_data` and `already_done` don't count; they are complaints about the
input. A contested rule returns after `contested_reset_days` (90) or as soon
as the client's thresholds change.
