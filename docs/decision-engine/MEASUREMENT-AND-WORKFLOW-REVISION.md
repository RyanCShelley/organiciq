# Measurement and workflow revision — 17 October 2026

## Work selection

Review strategy → check individual interventions → approve selected actions → assign and send to Teamwork.

A recommendation heading groups related work; it is not an extra decision or a purchased action. Each checked intervention counts once, including distinct work on the same page. Three interventions on one page plus two on another consume five actions and can have five delivery identities. Duplicate interventions on the same page are refused. Capacity is validated against checklist length, including older bundled briefs, rather than counting page briefs.

Saved approvals/history are preserved. On editing a selection, editable older bundles become individual actions. Assigned/sent/shipped work keeps its identity and scope. A page already selected for retainer work still conflicts with growth work. Existing approved bundles remain delivery bundles until edited; their individual interventions are counted honestly.

## Visibility

The primary view lists each tracked keyword, position, actual ranking URL and observation date. Prompt mentions and citations are a separate view with provider and date. Missing readings remain unknown. Keyword readings use the newest dated observation on/before the assessment date; multiple engine observations currently use the newest per term. This does not establish complete market coverage or combine keyword rankings with AI presence into a single score.

## Traffic

GA4 sessions measure actual site visits. Show all ingested channels, with organic search, direct/unattributed, AI referrals and other channel rows. The all-channel figure is the total, not an additional channel. Prior visits use an equally sized preceding window. Missing data is distinct from measured zero. Direct is not automatically credited to organic or AI.

The assessment adds an all-channel session trend. Search-impression divergence compares organic search visits only. CTR is an additional reference diagnostic, not the traffic score or proof of recoverable visits. Unmatched device/SERP CTR context blocks that diagnostic from selecting the traffic constraint.

The bounded CTR-gap calculation is shortfall / (shortfall + earned clicks), not shortfall / earned clicks. It is still an estimate, not observed loss. Earlier saved calculations are labeled superseded, and retained in history.

## CTR source

User-supplied industry averages as calculated up to 2026. Original filename: `ctr-study-ctr-by-position_desktop_all_2026-09_vs_2026-08.csv`. Stored unchanged as `apps/api/app/decisions/data/ai_overviews_desktop_2026_aug.csv`. Its actual value column is `AI Overviews, Aug 2026`, positions 1–20. Values include 7.52% at position 1 and 11.2% at position 2; no monotonicity adjustment is imposed.

This is exposed as an explicit desktop AI Overview reference scenario and visible in the live UI. It is not silently substituted for mobile, unknown-device or non-AIO results, nor used as a guarantee for one client's query. Existing broad CTR-based snippet opportunities remain reference estimates requiring human review; full per-query/device/SERP calibration remains future work.

## Leads

The user explicitly selected actual lead conversion rate versus a target rate. The current measurable proxy is configured GA4 lead event counts / all-channel GA4 sessions × 100, with identical period and channel scope. This may count repeat events and is labeled a lead event rate; unique/qualified lead rate requires a suitable source. Missing event observations are not automatically zero.

An explicit editable client target lives in `DecisionThreshold.thresholds.target_lead_rate_pct`. It is not inferred from a monthly lead-count goal or old baseline. No configured target means no rate-goal judgment. Target changes affect future assessments; saved assessment history is preserved. The current target can also be compared with a saved actual rate in the UI, explicitly labeled current target.

## Preview and validation

The sample company's measurement rows are synthetic and labeled as such. Its saved plan and approval history are preserved. No production integrations or external Teamwork task creation are enabled in that sample. Regression tests mock external delivery.
