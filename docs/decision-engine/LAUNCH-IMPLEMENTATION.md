# Reviewed decision engine launch implementation

Implemented locally October 17, 2026. This is an application change, not a production deployment.

## How the decision screen now works

The engine still saves an assessment and its suggested focus. Staff can record the strategy, select Visibility, Traffic, Leads, continuing strategy or insufficient evidence, and explain the decision. The selected focus does not require a failing branch.

The review panel offers six action families: priority-page improvement, AI answers and citations, internal links, conversion path, structured data and investigation. It collects every applicable finding rather than exposing only the first rule that matched. Missing keyword volume does not remove findings from review. Page-ownership findings appear separately and consume no growth slot.

Staff select, edit and order briefs, or create a manual strategic brief. Adding another finding on the same page combines its checklist and evidence into the selected brief. The reviewer still chooses the final scope, completion criteria and measurement. Approval checks capacity and duplicate pages, including active retainer work. Remove conflicting retainer work through its existing plan controls before approving growth work on the same page.

Saving changes creates a draft. Approval saves a version with the actor, time, strategy, focus and exact briefs. Reruns preserve the review and approved history. Sent/shipped briefs cannot be rewritten or removed, and an assigned brief must be unassigned before changing scope. Stale writes from another browser window are refused. The legacy growth add/remove endpoint cannot change a reviewed plan.

Growth assignment, shipment and Teamwork delivery require approval on new or reviewed records. Existing legacy workflow remains supported. Both copied and sent briefs include checklist and evidence. No tasks were sent as part of implementation or verification.

## Keyword and prompt targets

The decision screen now includes a combined target list populated from tracked keywords, existing mappings, tracked prompts and manually added items. Each has an existing-page, planned-page, unmapped or excluded state, a priority flag and a decision note. Existing keyword mappings are preserved; edits from the legacy keyword-map editor keep the unified target state in sync.

Prompt observations can be recorded with the provider/model, observation date, actual response, brand mention, client-domain citation and citation URL. Unknown is distinct from false. Observed mention/citation gaps on mapped prompts become reviewable AI findings on a rerun. A deliberately planned keyword- or prompt-led page can enter the existing new-content pool without a keyword-volume requirement. New page descriptions shared by multiple targets are grouped by their explicit plan note.

The Hugging Face tester is not directly connected. There are no automated external prompt runs or a verified provider adapter in this release. Record actual observations through the form/API; direct ingestion and scheduling remain separate integration work.

## Measurement corrections

- All-blocked assessments report insufficient evidence instead of visibility expansion.
- V4 assesses only mapped declared pages and checks that the intended normalized URL actually ranks. Unknown mapping is not a ranking failure.
- Title rewrite findings require an explicitly primary term.
- Keyword candidate loading can use tracked-keyword volume when the metrics table has none.
- Triage CTR calculations use impression-weighted positions, consistent with page candidates.
- Latest visibility/AI summary reads and relaunch annotations are bounded at the assessment date.
- CTR, opening and conversion-route explanations distinguish observations from proposed causes. The AI format finding no longer claims prose cannot be cited.
- Results iterate approved growth work. Draft edits retain the last approved version for measurement. Unshipped or skipped work is not judged. Recording shipment captures the baseline immediately before shipment and starts the configured waiting period. Measuring a metric never marks an action complete; recording shipment does.
- Conversion metrics are labelled as page-local lead events per landing session, not downstream landing-session attribution. Prompt citation checks remain manual unless an appropriate measurement is explicitly selected.

## Rollout

Apply database migration `0064_watch_targets` using the normal API release migration process (`alembic upgrade head`). It adds a table and preserves existing keyword maps and monthly records. Review state and version snapshots live alongside the assessment in the existing monthly record JSON.

Open a client's Decision Engine, review the target list, then rerun a finished month to populate all findings. Existing runs can enter the review workflow immediately using their stored candidates; legacy selected work retains its action identity so existing assignments remain associated. New prompt observations appear in findings after a rerun.

Before production release, review representative client plans with the account lead. The change does not establish that a particular action will cause growth.

## Validation and remaining scope

API regression tests cover review persistence, focus independence, approval, stale writes, capacity, duplicate interventions, task-delivery gating, grouped findings, individual task selection, target states, shipment-based results and migration/model consistency. Frontend unit checks, TypeScript, lint and a production webpack build were also run. Existing lint warnings are outside the changed components. The default Turbopack build encountered a local process-permission error; webpack completed successfully.

This release does not implement the entire future design: full historical reconstruction of every keyword/crawl input, seasonal comparison controls and a holiday calendar, richer CTA inventories, journey analytics, autonomous paid-media changes, and direct LLM-tester integration remain separate work. Existing CTR thresholds and the funnel ladder remain assessment heuristics; they no longer control the human-reviewed growth plan. FAQ/entity markup findings are available for review, and should not be interpreted as guaranteed search or AI citation gains.

Production compatibility: older saved assessments receive the new measurement display from stored facts for their historical month on read. Their recommendations and approval history are not rewritten; no integrations are rerun.
