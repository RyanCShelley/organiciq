# OrganicIQ Decision Engine — handoff for Claude Code

This folder holds what Claude Code needs to rebuild the decision engine's triage logic and its client page.

```
docs/decision-engine-spec.md       The triage rules: constraint selection, target scoring, action catalog, plan slots, spillover, suppression, data backlog
docs/client-page-spec.md           The client Decision engine page: layout, data binding, behaviour, acceptance criteria
design/client-page.html            Reference design (open in a browser; assign / skip / send work)
schema/monthly-record.schema.json  The saved monthly record the engine writes and the page reads, plus the engine_actions workflow row
schema/example-record.aquaman.json Example record matching the reference design
```

## How to use this with Claude Code

Copy this folder into the repo (suggested: `docs/decision-engine/`), then start Claude Code in the repo with this prompt:

> Read `docs/decision-engine/README.md` and every file it lists. Then explore the existing decision engine code, the ingestion jobs and the database schema (tables named `facts_*`, `clients`, `conversion_definitions`, `client_conversion_pages`, `decision_thresholds`, `channel_rules`, `refresh_queue`, `annotations`). Before writing code, give me a plan that maps each rule in `decision-engine-spec.md` to the code that implements it today (or says it's missing), lists schema changes, and lists anything in the spec that conflicts with the codebase. Wait for my OK.

## Suggested build order

1. **Schema.** Add `keyword_targets` and `engine_actions` tables; add the monthly record table (one row per client per month, JSON per `monthly-record.schema.json`). Seed `decision_thresholds` with the spec's defaults.
2. **Engine, Decision 1.** All 11 tests (V1–V5, T1–T3, L1–L3) with pass / fail / blocked, the relaunch override, two-month hysteresis, incident routing. Unit-test each test against fixture data.
3. **Engine, Decisions 2–3.** Scoring per branch, plan slots (Launch 1, Lift 3, Lead 5, Enterprise ≥5), spillover to the next failing branch only, one action per URL, no padding, suppression rules, confidence + reasons.
4. **Save the record.** The engine runs monthly (and on demand from the admin board only) and saves the record. The page never recomputes.
5. **Client page.** Build to `client-page-spec.md`, matching `design/client-page.html` inside the existing app shell. Replace the current page's date picker, Run Engine button, branch action counts and "advice, not a rule" copy.
6. **Workflow.** Assign / due / skip / send writes `engine_actions`; Send creates tasks for assignees.
7. **Results loop.** A daily job fills `before_value` / `after_value` / `result` on check dates and surfaces them as `previous_results` in the next month's record.

## Rules that must hold (test these)

- A passing or blocked branch never gets an action in a slot.
- Leftover slots go to the next failing branch, in Visibility → Traffic → Leads order, flagged `spillover`.
- Actions never exceed the plan's slots; fewer qualifying targets means fewer actions.
- Lead targets need ≥ 100 managed sessions; below that only as a last resort, flagged `small_sample`, and confidence drops to low.
- Site-wide technical faults are incidents, not slot actions.
- Stale GSC or GA4 data (> 7 days) → client Withheld, no actions.

## Not in this folder yet

- **Admin board** (portfolio view across all clients: constraint mix, slot usage, data readiness, results). A working prototype exists as a separate dashboard; build it after the client page.
- Open questions are listed at the end of `decision-engine-spec.md`.
