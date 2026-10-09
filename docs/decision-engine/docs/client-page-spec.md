# Client Decision Engine Page — UI Spec

Route: the existing **Decision engine** item in the client sidebar (Account section).
Reader: the agency owner, who reviews the month's plan and assigns it to the team. Clients do not see this page.
Reference design: `design/client-page.html` (open in a browser; assign/skip/send work).

## Job of the page

Answer three questions in order, then let the reader act:
1. What is this client's one constraint this month, and why?
2. Can I trust it? (confidence + what to check)
3. What are the actions, and who does each one? → assign → send.

## Changes from the current page (must fix)

| Current | New |
| --- | --- |
| Date picker "Last 30 days" + "Compare: previous period" | A **Run** selector of saved monthly records (Oct 2026, Sep 2026…). The page never recomputes the engine. |
| "Run Engine" button on the client page | Removed. Re-running lives on the admin board only. |
| Three rankings in conflict (subtitle "ranked by expected leads", table "constraint first, then by how many people", copy "the ranking is advice, not a rule") | One rule, stated once: slots fill from the constraint, leftovers spill to the next failing branch. Delete the "advice, not a rule" copy. |
| Passing branches get action counts ("Visibility · 2 actions") | Passing branches never get slots. Their candidates appear under **Not this month**. |
| "Do this first" badge on an item below the plan line | Site-wide technical faults are **incidents**: own card, "Doesn't use a slot", own assignee. |
| Branch tiles "43% of 30% bar" with no metric name | Each tile: branch name, Pass/Fail/Blocked chip, value, **metric label**, pass line ("pass at 30% or more"). Leads shows counts ("4 of 50 leads") when the test is goal pace. |
| Action rows titled with the problem + full URL repeated | Verb-first title, path once, then Why this page / Done when / Effort / Measured by / Check on. |
| "People / mo" column mostly "—" | Removed. Evidence lives in "Why this page". |
| No confidence signal; 34-session target shown as #1 | Confidence chip + **Check before you assign** box listing each reason (goal looks misconfigured, small sample, fallback used). Small-sample targets carry a flag chip. |

## Layout (top to bottom)

1. **Top bar** — "Decision engine"; subline "October 2026 run · saved Oct 1 from data through Sep 28 · next run Nov 1"; Run selector.
2. **Review bar** — left: "N of M assigned" / "Ready to send" / "October plan sent" + one helper line. Right: **Send plan to team** (primary, disabled until every action and incident is assigned or skipped).
3. **Constraint card**
   - Eyebrow "THIS MONTH'S CONSTRAINT", constraint name (large), one-sentence reason with the failing numbers, and how slots were filled.
   - Facts: Plan + slots, Held since (month n), Confidence chip.
   - Warning box (only when confidence is low or flags exist): numbered checks.
   - Three branch tiles in Visibility, Traffic, Leads order. The constraint tile is emphasized (strong border, filled "Fail · constraint" chip). Blocked tiles say what is missing.
   - Expandable per tile (nice-to-have): all tests in that branch with value vs pass line.
4. **Growth actions to assign** — heading + "Launch plan: 1 slot, filled from the constraint".
   - One card per slot, in slot order: `Slot n · ID`, branch chip, flags (Spillover, Small sample), verb-first title, path (mono), Effort / Measured by / Check on, Why this page, Done when, then **Assign to** (team select), **Due** (date, default run date + 7), **Skip this month** (asks for a reason, logged).
   - Empty slot card (dashed): "Empty slot" + reason, e.g. "No qualifying target left in a failing branch. Leads is blocked, so it can't take this slot."
   - Incident cards after the slots: "Technical baseline · incident", "Doesn't use a slot", title, scope/effort line, Assign to.
5. **Not this month** — candidates that didn't get a slot, each with branch + status chip and the reason ("Visibility passes, so it can't take a slot").
6. Two cards side by side:
   - **Last month's results** — action, before → after, result chip (Improved / No change / Worse / Waiting). Empty state: "Nothing was logged for September. Results appear 28–45 days after an action ships."
   - **Data that limited this run** — chips for each gap (missing/partial/stale).

Withheld state: constraint card shows "Withheld", the reason (e.g. "Search Console data is 11 days stale"), every slot card reads "Withheld", Send is hidden.

## Data binding

Everything renders from the saved monthly record (`schema/monthly-record.schema.json`):

| UI | Field |
| --- | --- |
| Run subline | `month`, `run_saved_at`, `data_through`, next run = first of next month |
| Constraint name / reason | `constraint`, `reason_text` |
| Plan / slots / held since / confidence | `plan`, `action_slots`, `held_since`, `confidence` |
| Check-before-you-assign | `confidence_reasons[]` |
| Branch tiles | `branches[]` → headline test per branch (`headline_test`), its `value`, `metric_label`, `pass_line`, `direction`, `status` |
| Action cards | `actions[]` |
| Empty slots | `empty_slots[]` |
| Incidents | `incidents[]` |
| Not this month | `not_this_month[]` |
| Results | `previous_results[]` |
| Data gaps | `data_gaps[]` |

Workflow fields (`assignee`, `due`, `status`, `skip_reason`, `sent_at`) are written back to `engine_actions`, not to the run record. Team list comes from the org's users.

## Behaviour

- Assign → saves immediately (optimistic). Changing a sent plan re-enables Send ("Send changes").
- Send plan → creates tasks for each assignee (Teamwork or the internal task system), sets `status = assigned`, stamps `sent_at`.
- Skip → requires a reason (select: "Already done", "Client declined", "Wrong target", "Other" + text); the slot is not refilled.
- Run selector on a past month is read-only except results.

## Visual

Match the existing app shell: slate sidebar (#1E2B37), green accent (#15784F text/buttons, #3DD68C logo), white cards on #F4F6F7, 12px radius, 1px #E1E6EA borders. Status colors: pass #15784F on #E5F4EC, fail #B4441C on #FDF4F0, warning #8A4B08 on #FDF1E3, Visibility info #2C4A86 on #E9EEF8. Paths in a monospace face. Touch targets ≥ 44px. All controls are real `<select>`, `<input>`, `<button>`.

## Acceptance criteria

- A Launch client never shows more than 1 slot card; Lift 3; Lead 5; Enterprise per override.
- No passing or blocked branch ever has an action in a slot.
- Spillover actions show the Spillover chip and the branch they came from.
- No action is shown without why, done-when, metric and check date.
- The page makes no engine calls; reloading shows the same plan.
- Send is disabled until all slot actions and incidents are assigned or skipped.
- Works at 390px wide: sidebar stacks, cards single column, no horizontal scroll.
