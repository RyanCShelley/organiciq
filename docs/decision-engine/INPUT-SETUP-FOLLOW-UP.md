# Input setup and automatic ownership

Local follow-up to the monthly-review release. Production inspection of ACCTek found 20 September keyword observations, one in the top 10, and no priority flags in the evidence view. The overview's priority-only filter hid this measured data. It now uses measured tracked keywords when a priority cohort is unavailable and labels the scope explicitly. Missing dated readings and missing tracked terms have separate messages.

## Monthly visibility

Use the same terms with dated readings in both calendar months. Report position movements and top-10 entries/exits. With at least five paired terms, the monthly movement diagnostic replaces the need to wait for a 90-day site score. Its review rule is more than 30% losing at least three positions; it is evidence for human review, not a proven business constraint. With fewer pairs, individual movements remain visible. A comparable 90-day provider score is a fallback; Search Console impression trends are a separate supporting signal.

A current SE Ranking site-summary endpoint is dated when observed, even in a historical backfill. It cannot reconstruct a past score by changing the date. Existing observations are not rewritten.

## Lead rate

The baseline workflow accepts and saves an explicit target lead conversion rate alongside the count goal. Existing baselines can set/update the rate without relocking; blank during a rebaseline preserves an existing target. The chosen target is stored with the frozen version when supplied. The measured baseline is never silently promoted into a growth target. Missing target and missing observed rate have separate explanations.

## CTR

Match stored GSC query/page observations to dated desktop US DataForSEO observations with an AI Overview. Use the supplied AIO desktop reference only for that subset. Report matched impression/query coverage and require 100 matched impressions for the diagnostic. Newer snapshots without AIO supersede older ones; future, stale, other-device and other-market observations do not qualify. No billable pull runs on page load.

## Automatic keyword map

Monthly assessment saves build supported ownership from stored page topics, rankings and GSC evidence. The map's Build / refresh action additionally runs the existing subject matcher. Automatic ownership has source `auto`; explicit saves become `confirmed` and always win, including deliberate no-page and excluded/planned states. Conflicting sources stay unresolved. The mapper validates indexability, canonical destination, client domain and path. It does not invent term primacy or strategic priority.

Migration `0065_automatic_keyword_map` adds the distinct source. Gaps are the default map view; every populated mapping can be overridden. Human approvals and previously sent work are unchanged.

## Full review after this workflow settles

Review the full source-to-outcome path: source freshness and historical dates; distinctions among keyword tracking, page ownership, priorities and prompts; eligibility and specificity of each action; count versus rate goals and channel scope; capacity and independent delivery; approval/rerun/history behavior; actual results attribution; and duplicated map/watchlist/setup interfaces. Identify what can be removed after tracing each consumer. Do not discard useful ownership data merely because ranking visibility should work without it.
