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
