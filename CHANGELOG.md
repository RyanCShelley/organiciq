
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
