# Decision engine review and launch proposal

Reviewed October 17, 2026 against local commit `595954c`.

## Conclusion

The current engine is useful as a source of findings, but its selection logic does not support the way you want to run strategy. It turns incomplete observations into a mandatory funnel priority, filters the available work through that priority, and often presents one possible fix as an established diagnosis. Changing thresholds alone will not correct this.

The proposed operating model is: collect evidence across keywords, prompts and pages; show findings and their limitations; let you select the constraint against the client's strategy; assemble a short plan you can edit and approve. Preserve the data integrations, saved runs, workflow and task delivery infrastructure.

This is a code review and implementation proposal. Application behavior has not been changed. The supplied review and its Word comments were treated as review material, and your chat request as the instruction. Neither historical client counts nor production state were independently verified.

## Scope and verification

Traced monthly orchestration, triage and signal loaders, keyword mapping and matching, target scoring, the growth action catalog, slot allocation, update and new-content logic, manual plan controls, persistence and results measurement. This covers the decision path; it is not a line-by-line audit of every integration, crawler or unrelated application feature.

Ran six standalone assertions against the existing pure Python functions. They confirmed the override allocation failure, all-blocked expansion fallback, scale-insensitive T1 failure, missing-volume target removal, unknown-role title rewrite, and V4's declared-page failure. These are behavior reproductions, not regression tests for a new implementation. The full pytest suite was not run: the available Python lacks pytest and is 3.14, whereas the repository specifies 3.13 and database fixtures require a dedicated test database.

## What the existing review gets right and what needs correction

| Review statement | Finding in this checkout |
| --- | --- |
| Visibility comes before Traffic and Leads | Confirmed. The first failing branch wins; a recent relaunch forces Visibility. |
| Visibility is entirely keyword-map based | True for growth action candidates, but not all diagnosis: V5 already uses AI prompt checks and tracker statistics. There is no equivalent prompt-to-target action pipeline. |
| Mapping is locked to GSC | GSC suggestions win when present, but a semantic subject matcher already supplies fallback suggestions. Confirmed mappings are human decisions. The limitation is GSC precedence and keyword-only scope, rather than complete dependence on GSC. |
| PR 24 fixes V4 | That fix is absent from this checkout. V4 can still fail a declared conversion page with no mapped evidence. No claim is made about remote PR or deployed status. |
| L-1 says conversion elements equal zero | Current L-1 correctly cites missing in-content links. The conversion-elements evidence belongs to L-2. Old saved records can still contain older wording because the UI reads saved records. |
| A manual constraint override exists | Storage and reading exist, but no route or user-facing editor for creating the constraint override was found. More seriously, slot allocation does not honor a selected branch unless it fails. |
| L2 needs a baseline | Confirmed in the signal loader. Whether every client's baseline is currently empty requires checking the database. |

## Findings that matter before launch

### 1. Strategy selection is subordinate to the test ladder

`decisions/triage.py:522` chooses the first failed branch, forces Visibility for relaunches, and falls back to `visibility_expansion` when nothing fails—even when every branch is blocked. The fallback text talks about new keyword groups and prompts, but the growth allocator has no corresponding expansion selection path.

`services/monthly_run.py:378` applies a manual constraint without changing test statuses. `decisions/slots.py:129` then admits the selected branch only if its status is FAIL. A user selecting Leads with passing Leads tests can therefore get no Leads slots. The headline and plan can disagree.

Replace mandatory selection with a review state. Store the system's suggested focus separately from your selected constraint, rationale and strategy period. A valid finding may be selected from a healthy or partially measured branch. Missing evidence should block only the conclusion or action that needs it. A relaunch should be context to review, rather than an automatic six-month strategy command.

### 2. Prompts are observations without strategic page ownership

`services/triage_signals.py:188` reads AI tracker presence; `models/seranking.py:265` already stores tracked prompts, brand mentions, citations and citation URLs. But `services/target_signals.py:213` starts from confirmed keyword targets, and `decisions/targets.py` represents keyword candidates. There is no prompt equivalent of the confirmed target mapping in this path.

An AI visibility failure can therefore select Visibility and receive keyword title or schema work without evidence that those actions address the failing prompts. That disconnect is more serious than simply missing another metric.

Make the watchlist the source of strategic intent. Give keywords and prompts explicit target states: existing page, planned page, needs mapping, or intentionally excluded with a reason. Every active item should have an accountable target state; absence of a page must remain visible without inventing a URL. Many keywords and prompts can belong to one page. A prompt can require support from other pages or external sources, so target ownership must remain separate from observed citations.

Keep observed ranking URLs, GSC associations, semantic suggestions and AI citation URLs as separate evidence. GSC should not silently win the decision about which page ought to serve an intent.

### 3. Volume and heuristics silently decide which options you can see

`services/target_signals.py:290` takes volume only from the keyword metrics table, although the mapping view in `services/decisions.py` can fall back to tracked-keyword volume. `decisions/targets.py:172` converts absent volume to zero; `rank_candidates` drops zero scores. A term can show volume in the mapping interface yet disappear from growth recommendations. This is also incompatible with prompts, whose importance need not have a keyword-volume estimate.

The score's supposed page intent is supplied by `classify_page_url(url)` in `services/target_signals.py:297`. That function uses URL heuristics, and this call does not pass declared conversion pages. The current implementation therefore does not justify describing intent as a confirmed page classification.

Retain important targets with missing measurements in the review queue. Show business priority and evidence confidence independently. Use confirmed strategy and page intent first; use volume as supporting evidence within comparable keyword opportunities. Do not multiply prompt priority by search volume or sort incomparable branch scores as if they shared one unit.

### 4. Findings overclaim what measurements prove

T1 uses a benchmark to estimate expected clicks; missed clicks are an estimate, not measured lost demand. `services/triage_signals.py:243` also averages daily positions without impression weighting, while page candidates use weighted positions in `services/page_signals.py:115`. Diagnosis and prescriptions can disagree before any judgment is applied.

T1 has no absolute opportunity or evidence-volume floor. The reproduced 58/72 and 5,800/7,200 examples fail identically. T1 includes page shortfalls across positions and navigational traffic, while T-1 excludes navigational pages and positions below the top three. Diagnosis and action eligibility therefore cover different populations.

The language in `decisions/catalog.py:548` treats the remaining CTR gap as the snippet's fault, and `:593` treats low engagement as an opening mismatch. Neither cause follows from those metrics alone. Likewise, the absence of entity properties, an FAQ phrase, or an exact keyword phrase does not establish the highest-value growth intervention.

Show observations separately from hypotheses: “CTR below this reference; inspect intent and search results” or “engagement below comparison; review landing experience.” Offer snippet, content, offer or measurement work after review. Align windows and position calculations. Record absolute volume, reference cohort and limitations; select minimum evidence requirements deliberately rather than introducing another unexplained universal cutoff.

Do not simply extend title rewrites to all positions. Pages ranking 4–20 need a review path that can lead to snippet, content or visibility work according to the evidence.

### 5. Mapping completeness is mistaken for visibility performance

V1 measures only priority confirmed targets that join to tracked keywords. It does not show whether that subset represents the full strategic watchlist. V4's `reached` set uses priority mappings only, tests mapped-term position rather than verifying the intended URL actually ranks, and compares target URL strings directly (`services/triage_signals.py:117`). A term ranking on the wrong page can make its intended page look reached; missing mappings can make another page look invisible.

Report tracking and mapping coverage separately from observed performance. “Not measured,” “not mapped,” “ranking URL differs,” and “target observed out of reach” are different findings. Test intended-page reach against normalized observed URLs. Populate denominators from the selected watchlist, without counting missing rank checks as proven ranking failures.

### 6. The options interface is helpful but still hides choices

`OptionsPanel.tsx` and the in-plan endpoint already let staff include or remove generated candidates. Reuse this work. However, `prescribe` and `prescribe_page` return only the first matching action. Earlier rules hide later possible remedies; targets removed before prescription never reach the options panel. In particular, an unknown term role can trigger V-1 because its guard excludes only explicit secondary terms.

Manual inclusion also lacks a capacity check in the in-plan route, and candidate additions can select multiple jobs on the same URL. The frontend helper sorts added options by scores from different units. These controls do not yet deliver a coherent reviewed plan.

Collect all valid findings, group them by page and intent, and expose the underlying evidence. Build one editable page brief from selected findings. Keep plan capacity visible, with an explicit way to record an agreed exception. Let you order work directly, and add a strategic action that has no metric-triggered candidate yet. Require an explicit primary role before suggesting a primary-term title rewrite.

### 7. Missing and historical evidence are not consistently isolated

The entire run is withheld when GSC or GA4 is absent or stale (`services/monthly_run.py:206`), even if current rank, prompt or crawl evidence could support independent findings. Conversely, historical reruns can use current keyword facts, latest crawl, latest AI statistics and latest visibility summary. Several queries have no upper bound at the run date. `_relaunched_recently` has a lower date bound but no upper bound, so a later annotation can influence an earlier run.

The AI share-of-voice trend test exists in the pure rules, but `visibility_signals` does not supply either share-of-voice field. That diagnostic is effectively unwired in this path.

Use evidence validity per source and per finding. Distinguish a saved run snapshot from a historical reconstruction: store exact source dates and versions; use historical facts at or before the assessment date, or explicitly disclose where history cannot be reconstructed. Missing data should create a measurement task or a limitation, rather than suppress unrelated work or manufacture a pass.

### 8. Lead and outcome measurement need more precise meaning

L-1 has sensible stage and offer guards, and lead candidate ranking requires positive sessions. It still has no meaningful opportunity floor beyond that, and route absence can be inferred from an empty link set without an explicit successful-capture flag. A missing link is a possible improvement, not proof that conversion is the business constraint.

`services/results.py:261` divides events recorded on a page by sessions landing on that URL. That does not establish leads attributable to sessions that started there and converted elsewhere. L-1's promise of measuring leads from sessions starting on the page overstates what this join demonstrates.

The result iterator (`services/results.py:396`) reads saved slotted pools, rather than the effective plan after manual additions and removals. `check_due` uses the prescribed check date and can set an assigned action to done after measuring, independently of an explicit shipped event. As a result, newly selected work may miss measurement while removed work remains in the loop; metric movement and task completion can be conflated.

Persist the approved plan and iterate that plan for results. Separate shipped status, observed metric change and causal confidence. Anchor evaluation windows to shipment plus the chosen maturation period. Label page-local event rates accurately unless landing-session conversion attribution is actually available. Treat a missing lead baseline as an unavailable comparison, not a reason to prevent all lead work.

## Proposed launch experience

1. **Strategy.** Record the client's objective, priority services or topics, relevant audience, current initiative and exclusions. Keep this concise and editable. Display the strategy beside the findings rather than hiding it in settings.
2. **Watchlist.** Review all selected keywords and prompts, targets and coverage. Preserve provider identifiers and original prompt text. Missing maps and missing measurements stay visible.
3. **Findings.** Show Visibility, Traffic and Leads together. Each finding states what was observed, dates and sample, strategic relevance, possible interpretation, and what is unknown. Show the system's suggested focus as a suggestion.
4. **Your decision.** Choose the month's constraint after review and record why. Keep “insufficient evidence” and “continue current strategy” available instead of forcing expansion. Retain both the evidence and your decision.
5. **Plan.** Select and order a small number of page briefs, edit their scope, defer or reject findings, or add strategic work. Group related keyword and prompt issues into one brief. Preserve contracted growth, update and new-content allowances without making the user learn separate rule catalogs.
6. **Approval and execution.** Save a reviewed plan version before assigning or sending tasks. Reruns create a new proposal and show changes; they do not silently replace approved work. Carry assignments only when action identity and scope remain compatible.

## Simplify the actions

Use five user-facing action families, while keeping rule IDs as internal evidence references:

| Action family | Scope |
| --- | --- |
| Improve an existing page | Content, opening, query intent, title or answer sections selected for a specific reason. |
| Create a needed page | A confirmed strategic keyword or prompt intent needs a new destination. No invented prompt-volume requirement. |
| Improve the next step | Appropriate offer, in-content route, CTA or conversion experience. |
| Strengthen support and access | Relevant internal links, specific technical defects, or supported structured-data work. |
| Investigate or fix measurement | Validate mapping, search-result behavior, tracking, crawl coverage or an uncertain explanation. |

Each brief needs a target or planned-page reference, selected findings, your rationale, a short editable checklist, completion criteria, owner and evaluation method. Missing markup alone should not automatically consume a growth slot. Prompt findings may also require external-source or brand-representation investigation; do not force every AI visibility problem into an on-site edit.

## How to use the LLM visibility tester

Your tester is a candidate measurement source for the prompt watchlist. The Hugging Face landing page was accessible, but source and interface details could not be retrieved through the web tool. No claim is made that an API, batch interface or specific provider coverage has been verified, and no prompt runs were started.

First inspect the tester's actual source or export format. Then support a normalized import or adapter that records: client and brand, stable prompt identity, exact prompt, provider and model version, timestamp, locale, search or grounding mode, repeated-run identifier, answer, brand mention, brand citation, citation URLs, and errors or incomplete runs. Store target mapping separately from observed results.

Use consistent prompt sets and run conditions for comparisons. Show successful observations and denominators by engine; do not treat API failures as absence or combine providers into a percentage with an unclear denominator. A brand mention, a citation to the client's domain and a citation to the intended page should be distinct outcomes. Custom API runs should remain distinguishable from consumer ChatGPT observations. Start with an import and explicit runs; add scheduling after the measurement contract works.

## Recommended implementation order

**First: make the decision workflow trustworthy.** Separate assessments from selected focus; implement the focus control and saved rationale; remove failure-only gating from human selection; persist a reviewed plan; preserve it across reruns; group all findings into editable briefs; enforce capacity and page identity at the final plan layer. Correct the V4 coverage logic, missing-volume removal, unknown primary role, inconsistent CTR calculation and unsupported diagnostic wording.

**Second: complete the keyword and prompt watchlist.** Add target-state records with migration from existing confirmed keyword mappings. Preserve current maps, notes and priority flags. Include prompt targets, planned pages and explicit exclusions. Offer GSC, ranking, subject and citation evidence side by side. Wire prompt findings to the same review and brief workflow, and populate or remove the currently unwired AI trend.

**Third: validate measurement and launch.** Connect a verified tester import or adapter, implement source-specific validity and historical boundaries, and align results with approved and shipped work. Review representative clients with sparse maps, sparse traffic, missing baselines, active relaunches and prompt-only priorities. Validate the proposed decisions with you before broad rollout.

Do not spend the first release building a new universal opportunity formula, dozens of threshold controls or an autonomous LLM planner. Those would add another layer of assumptions before the decision ownership and evidence model are correct.

## Acceptance checks for the rework

- A chosen constraint can select supported work even when its branch is healthy or another branch lacks data; the original test findings remain intact.
- All-blocked data produces an insufficient-evidence assessment, not an expansion claim.
- Every active keyword and prompt appears in the watchlist with a target state. Missing volume does not erase strategic work.
- An unmeasured page is not described as invisible. A term ranking on a different URL does not prove its intended page has reach.
- Multiple findings on a page are visible and can be combined into one brief; no primary title rewrite is proposed from an unknown role.
- Historical assessment does not read later facts or annotations as contemporaneous evidence. Unsupported reconstruction is disclosed.
- Manual additions, removals and ordering survive reruns and feed assignment, delivery and results consistently. An approved plan is versioned.
- Capacity and duplicate-page checks apply to the final plan, with recorded intentional exceptions.
- Results start from shipment, do not auto-complete unshipped work, and describe event attribution and AI measurements honestly.

## Code map

Paths below are relative to the repository root.

| Responsibility | Source |
| --- | --- |
| Assessments and constraint selection | `apps/api/app/decisions/triage.py` |
| Evidence loading | `apps/api/app/services/triage_signals.py` |
| Orchestration and saved proposal | `apps/api/app/services/monthly_run.py` |
| Keyword map and suggestion precedence | `apps/api/app/services/decisions.py` |
| Semantic suggestions | `apps/api/app/services/keyword_matcher.py` |
| Keyword candidates and page facts | `apps/api/app/services/target_signals.py` |
| Keyword scoring | `apps/api/app/decisions/targets.py` |
| Page candidates and ranking | `apps/api/app/services/page_signals.py`, `apps/api/app/decisions/page_targets.py` |
| Action triggers and first-match selection | `apps/api/app/decisions/catalog.py` |
| Automatic allocation | `apps/api/app/decisions/slots.py` |
| Update and new-content work | `apps/api/app/decisions/update_catalog.py`, `apps/api/app/decisions/content_gaps.py`, `apps/api/app/services/content_gap_signals.py`, `apps/api/app/services/demand_gaps.py` |
| Saved state and mapping models | `apps/api/app/models/decision.py`, `apps/api/app/models/seranking.py` |
| Manual action inclusion | `apps/api/app/api/routers/decisions.py:315`, `apps/web/components/DecisionEngine/OptionsPanel.tsx` |
| Plan display | `apps/web/app/(app)/[clientSlug]/decision-engine/page.tsx`, `apps/web/lib/monthly-record.ts` |
| Outcome measurement | `apps/api/app/services/results.py` |
