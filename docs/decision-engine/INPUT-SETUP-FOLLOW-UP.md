# Input setup and automatic ownership

Local follow-up to the monthly-review release. Production inspection of ACCTek found 20 September keyword observations, one in the top 10, and no priority flags in the evidence view. The overview's priority-only filter hid this measured data. All active Watch List keywords now define the target set, regardless of legacy priority flags or page ownership. Excluded terms stay excluded. Rankings must be dated on or before the assessment. Prompts remain separate observations; no extra priority selection is needed. The overview and monthly trend use the same active Watch List scope.

## Monthly visibility

Use the same terms with dated readings in both calendar months. Report position movements and top-10 entries/exits. With at least five paired terms, the monthly movement diagnostic replaces the need to wait for a 90-day site score. Its review rule is more than 30% losing at least three positions; it is evidence for human review, not a proven business constraint. With fewer pairs, individual movements remain visible. A comparable 90-day provider score is a fallback; Search Console impression trends are a separate supporting signal.

A current SE Ranking site-summary endpoint is dated when observed, even in a historical backfill. It cannot reconstruct a past score by changing the date. Existing observations are not rewritten.

## Lead rate

The baseline workflow accepts and saves an explicit target lead conversion rate alongside the count goal. Existing baselines can set/update the rate without relocking; blank during a rebaseline preserves an existing target. The chosen target is stored with the frozen version when supplied. The measured baseline is never silently promoted into a growth target. Missing target and missing observed rate have separate explanations.

## CTR

Apply the user-selected supplied industry curve as the common reference across queries, devices and markets. No observed AI Overview or DataForSEO snapshot is required. The source remains labeled as a desktop August 2026 study: application as a planning reference does not prove a matching SERP or forecast visits. Query/page positions 1–20 are supported; require 100 reference impressions. Report covered/total query impressions and keep the numerator and denominator in the same subset. Page-action diagnostics use the same curve and supported position range. GA4 remains the source for actual visits.

## Saved diagnostics versus current setup

Saved assessments remain immutable. Current client-scoped settings are read separately when displaying their setup gaps. If a rate or conversion page exists now, explain that setup is configured and the assessment needs a rerun; do not request duplicate entry. Page reach distinguishes no declared pages from declarations without usable keyword mappings. History gaps for new clients remain history limits. No client ID, domain, target rate or conversion URL is hardcoded.

Regression coverage includes clients sharing the same keyword, different markets/devices, no AIO observations, incomplete/new histories, exclusion overrides, mixed legacy priority flags, future readings, and current settings isolated between clients.

## Automatic keyword map

Monthly assessment saves build supported ownership from stored page topics, rankings and GSC evidence. The map's Build / refresh action additionally runs the existing subject matcher. Automatic ownership has source `auto`; explicit saves become `confirmed` and always win, including deliberate no-page and excluded/planned states. Conflicting sources stay unresolved. The mapper validates indexability, canonical destination, client domain and path. It does not invent term primacy or strategic priority.

Migration `0065_automatic_keyword_map` adds the distinct source. Gaps are the default map view; every populated mapping can be overridden. Human approvals and previously sent work are unchanged.

## Full review after this workflow settles

Review the full source-to-outcome path: source freshness and historical dates; distinctions among keyword tracking, page ownership, priorities and prompts; eligibility and specificity of each action; count versus rate goals and channel scope; capacity and independent delivery; approval/rerun/history behavior; actual results attribution; and duplicated map/watchlist/setup interfaces. Identify what can be removed after tracing each consumer. Do not discard useful ownership data merely because ranking visibility should work without it.
