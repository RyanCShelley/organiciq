# Spec vs. the code today

Written 9 Oct 2026, against `decision-engine-spec.md` v2026-10-09 and `main` at `b055b40`.
Nothing here is built yet. This is the mapping the README asks for, and the
answer to "are we on the same page": **no, and not by a small margin.**

---

## 1. The headline

What is in the repo today is a **ranked list of findings**. What the spec
describes is a **monthly triage run with a saved record**. They are not the
same program with different styling, and the last several days of work have
been refining the wrong one.

| | Today | Spec |
|---|---|---|
| Unit of output | A finding, ranked against every other finding | One constraint, N slot actions, saved |
| How many actions | All of them; the UI draws a line at the plan allowance | Exactly N, where N is the plan's slots. Fewer if targets run out |
| Branch status | A ratio against a floor; the *worse* of two readings wins | 11 named tests; a branch fails if **any** test fails |
| Passing branches | Still contribute actions to the list | **Never get a slot.** Their candidates go to "Not this month" |
| Site-wide faults | Compete for slots as "preconditions" | **Incidents.** No slot, own card, own assignee |
| When it runs | On every page view, for whatever dates the picker says | Monthly, saved; the page renders the record and never recomputes |
| What the page is for | Reading a ranked list | Assigning work to people and sending it |
| Memory between months | None | `held_since`, hysteresis, check dates, `previous_results` |

The last row is the one that matters most. Today's engine has no idea what
it said last month. The spec's engine is built around that: a constraint
holds for two months, an action is not repeated on a URL before its check
date, and results come back 28–45 days later. None of that is possible
without the saved record, and the saved record does not exist.

---

## 2. Decision 1 — the eleven tests

A branch fails if **any** of its tests fails; blocked if any test lacks its
input and none fails. Today there is one ratio per branch and the *worse* of
two readings wins, which is a different rule and gives different answers.

### Visibility

| Test | Spec | Today | Verdict |
|---|---|---|---|
| V1 Priority-term coverage | < 30% of **priority-group** keywords in top 10 | `assess_visibility` top-10 share over **all** tracked keywords | **Partial.** No priority flag exists — see §6 |
| V2 Visibility trend | `visibility_percent` falls > 15% / 90 d | — | **Missing.** `facts_ser_site_summary` is ingested and unread |
| V3 Impression trend | Managed GSC impressions −15%, 28 d vs prior | — | **Missing** |
| V4 Priority-page reach | A conversion/target page has no term in top 20 | — | **Missing.** Needs `keyword_targets` |
| V5 AI answer presence | Brand in < 20% of prompts, **or** `ai_sov` −25% / 90 d | `assess_visibility` AI citation % at a 25% floor | **Partial.** First half only; threshold differs (25 vs 20); no SoV trend |

### Traffic

| Test | Spec | Today | Verdict |
|---|---|---|---|
| T1 Missed clicks | Missed clicks > 20% of **actual** organic clicks | `assess_traffic` clicks ÷ expected clicks, floor 0.60 | **Different formula.** Same inputs, different question |
| T2 Divergence | Impressions +10% while sessions flat/down | — | **Missing** |
| T3 Engagement quality | Engaged rate < 50%, or < 80% of 6-month median | — | **Missing.** Engaged sessions are ingested and unread here |

### Leads

| Test | Spec | Today | Verdict |
|---|---|---|---|
| L1 Goal pace | Leads MTD < 80% of **pro-rated** monthly goal | `assess_conversion` leads ÷ period goal, floor 0.80 | **Partial.** Window-based, not month-to-date pro-rated |
| L2 Lead rate | Managed lead rate < 80% of baseline | — | **Missing** |
| L3 Next-step flow | > 50% of sessions land on TOFU with no in-content link onward | — | **Missing.** `facts_crawl_internal_links` is ready and unread |
| No `conversion_definitions` → **blocked**, never passed | | Treated as "not measurable", then the ladder moves on | **Conflict.** Blocked and not-measurable behave differently |

**Also missing:** the relaunch override (`annotations` has **0 rows**),
two-month hysteresis, `held_since`, and "Visibility expansion" when
everything passes.

**Conflict to resolve:** today, when no branch is below its floor, the
*weakest by headroom* becomes the constraint and the page says "nothing is
broken, this is the softest spot". The spec has no such state — everything
passing means **Visibility expansion**. Mine should go.

---

## 3. Decision 2 — scoring

Spec: `score = volume × w_intent × w_group × reach(pos, KD) × fit`, a product,
so a zero on any factor removes the candidate.

Today there is no score. There is a per-layer **count** — searches, clicks,
sessions — and actions sort by it. Of the five factors:

| Factor | Status |
|---|---|
| volume | Present for keywords; **absent for prompts** (SE Ranking returns none, so a nearest tracked term is borrowed) |
| intent | **Missing.** Nothing classifies commercial vs informational |
| group | Group names exist on all 769 keywords; **no priority flag** |
| reach | **Missing.** Keyword difficulty is present for 2 of 24 clients |
| fit | **Missing.** Needs `keyword_targets`, which does not exist |

So Decision 2 is effectively 1 of 5 factors. The count I ship now is closest
to `volume` alone.

---

## 4. Decision 3 — slots, spillover, suppression

| Rule | Today | Verdict |
|---|---|---|
| Launch 1 / Lift 3 / Lead 5 / Enterprise 5+ | `tiers.growth_action_allowance` = 1/1/3/5/5 | **Correct already** |
| Never exceed the slot count | All actions are returned; the UI draws a line and shows the rest | **Conflict.** The engine must cap, not the page |
| Spillover to the next **failing** branch only | `order_by_constraint` ranks every layer; passing branches keep their actions | **Conflict.** Opposite behaviour |
| One action per URL per month | `_collapse_by_page` | **Present** |
| No repeat on a URL before its check date | `_settling_urls` (60 d, generic) | **Partial.** No per-action check dates |
| Never pad | Enforced, and the shortfall is stated | **Correct already** |
| Skip `refresh_queue` URLs | `_refresh_queue_urls` | **Present** |
| Skip non-indexable / redirect / soft-404 | Present as findings; not a suppression | **Partial** |
| **> 7 days stale → Withheld** | Readiness checks only that rows *exist* | **Missing — and this is the big one. See §7** |

---

## 5. The action catalog

The spec names 12 actions with stable IDs. Today there are 9 with different
IDs and different triggers. Only three line up cleanly.

| Spec | Today | Verdict |
|---|---|---|
| V-1 Term in high-value spots | — | Missing (Stage 4 in the old plan) |
| V-2 Answer block / FAQ + FAQPage | `3a` answer-first, `3b` FAQ gap, `6` prompt gap | **Three rules doing one job.** Merge under V-2 |
| V-3 Entity markup (`about`/`mentions`/`sameAs`) | `5a` entity fix (checks brand naming only) | Partial |
| V-4 Internal links to the target | — | Missing; `facts_crawl_internal_links` is ready |
| V-5 Extractable structure | — | Missing; needs SERP features |
| V-6 Re-homing ticket | — | Missing; needs `keyword_targets` |
| T-1 Rewrite title and meta | `2a` serp_ctr | **Matches** |
| T-2 Match the SERP format | — | Missing; needs SERP features |
| T-3 Realign to the audience | — | Missing |
| L-1 Route to the next step | `1b` CTA/onward link | **Matches** |
| L-2 Add or move a CTA | `1a` (partly) | Partial; spec wants *first-screen* position, crawl stores a count |
| L-3 Match the offer to the topic | — | Missing; needs `client_conversion_pages` |
| — | `2c` rank push | **Not in the spec.** Retire or map to V-4 |
| — | `ai_crawlers_unblock` | Becomes an **incident** |

---

## 6. Schema changes

| Change | Why | Size |
|---|---|---|
| `keyword_targets` (keyword, target_url, role, group, priority) | V4, V-1, V-6, the `fit` factor, `w_group` | New table + admin UI + per-client config |
| `engine_actions` (uid, client, month, assignee, due, status, skip_reason, sent_at, before/after/result) | The whole assign → send → results loop | New table |
| `monthly_records` (client, month, JSON per schema) | Nothing is saved today | New table |
| `decision_thresholds` seed | The spec's defaults are not loaded | Config |
| A priority flag on keyword groups | V1 says "priority-group"; nothing marks one | Column or config |
| `clients.lead_value` | Null everywhere; the Leads scoring factor is optional without it | Config |

`keyword_page_map` exists and is the closest thing to `keyword_targets`, but
it has no role, no group and no priority. Decide: extend it, or add
`keyword_targets` and retire it.

---

## 7. The data reality — every client is Withheld today

I ran the spec's freshness gate against all 24 clients. **None passes.**

| | Clients |
|---|---|
| Search Console rows at all | **6 of 24** |
| GSC fresher than 7 days | **0 of 24** (best is 10 days; SMA, ACCTek and Element 6 are 15) |
| GA4 fresher than 7 days | 20 of 24 |
| `conversion_definitions` set | **4 of 24** |
| `client_conversion_pages` set | **2 of 24** (Element 6 has 2, SMA has 1) |
| Keyword groups beyond "General" | 10 of 24 |
| A group marked priority | **0 of 24** — no such field |
| `annotations` rows (relaunch override) | **0** |

Under §9 of the spec, every client is Withheld with a list of gaps. That is
the correct behaviour — serving actions off 15-day-old Search Console data is
worse than saying nothing — but it means **the P1 data backlog is the project,
not the engine.** Building Decision 1 against this data produces 24 Withheld
cards.

The 429 problem I flagged yesterday is part of this: ACCTek's crawl is being
rate-limited and reporting our throttling as 60 broken pages. The spec's P1
line "re-crawl with sections + faq_questions: 1–2 concurrent, back off on
429, honour Crawl-delay" is the fix.

---

## 8. Decisions taken (9 Oct 2026)

All six settled with Ryan. These are the rules; where they differ from the
spec, the decision wins and the reason is recorded.

**1. Nothing failing → Visibility expansion.** "Weakest by comparison" is
deleted. The engine will no longer name a constraint when no branch is below
its line; everything passing means the next tier of keyword groups and
untracked AI prompts become visibility targets. Removes `by_comparison` from
`Constraint` and the "softest spot" copy from the band. Two clients sit in
that state today (Popfoam, Robinson Unmanned); both have two unmeasurable
branches, so under the new rules they are blocked rather than passing.

**2. A blocked branch is skipped, not fatal.** Blocked is not failing, so the
ladder passes over it and the first genuinely failing branch becomes the
constraint — Visibility blocked and Leads failing means Leads. The blocked
branch shows as Blocked with what is missing, and cannot take a slot. This
matches today's behaviour, so no client's constraint changes on this alone.
The run still loses confidence through the spec's `missing_input` reason, so
the blocked branch surfaces in "Check before you assign" rather than in the
constraint choice.

**3. The count column goes.** Deleted from the card entirely; the evidence
becomes a sentence in "Why this page". Against real data the column was blank
on 25 of SMA's 26 rows and 10 of Element 6's 14, which is the spec's
complaint exactly. `score` stays in the saved record and orders the slots
without appearing on screen.

**4. 3a, 3b and 6 stay as three rules.** They keep their own triggers and
cards and all three write `V-2` into the record's `id`, which keeps the
record valid against the closed enum. Consequence to handle: three triggers
can fire on one page, so the one-action-per-URL rule arbitrates between them
rather than the rules being mutually exclusive by construction.

**5. Hysteresis starts from the first saved run.** The first record stamps
`held_since` to its own month and the two-month hold begins there. No history
is backfilled — SE Ranking keeps no per-month keyword history, so a backfill
would have invented the Visibility branch, which is the one that gates the
other two. Month-1 constraints can move freely; the rule is fully in force by
the third run.

**6. `keyword_page_map` becomes `keyword_targets`.** One migration: add
`role` (primary/secondary), `group` and `priority`, rename the table and
rename `page_url` to `target_url`, carry the two existing SMA rows. Keeps the
admin screen and the term-to-page suggester already built, which is what will
fill ten priority terms each across 24 clients.

## 9. What I would build first

Not Decision 1. The engine cannot be judged while every input is stale.

1. **Fix the crawler and the GSC pull** (spec P1). Back off on 429, honour
   `Crawl-delay`, and find why 18 of 24 clients have no `facts_gsc_pages`
   rows. Without this nothing downstream is real.
2. **`keyword_targets` + priority groups**, with the admin UI to fill them.
   This unblocks V1, V4, V-1, V-6 and two of the five scoring factors.
3. **`conversion_definitions` and `client_conversion_pages`** for the clients
   that will have a Leads branch at all.
4. **Then** the monthly record table, Decision 1's eleven tests in shadow
   mode, and the page rebuilt to `client-page-spec.md`.

Steps 1–3 are config and ingestion, not engine work. They are also the
difference between an engine that is right and an engine that looks right.

---

## 10. What I got wrong

Worth saying plainly, because it explains the last few days. I was handed a
synopsis in plan mode and built a constraint *selector* — one ratio per
branch, a floor, and a ranked ledger underneath. That was a reasonable
reading of what I had. It is not what this spec describes, and every
refinement since has been polish on an engine with the wrong shape:
per-layer units, a borrowed prompt volume, a "softest spot" constraint, a
precondition chip competing for slots. Most of that comes out.

What survives: plan slots, no padding, `_collapse_by_page`, the refresh-queue
suppression, the crawler's `sections` and `faq_questions` capture, the
measured CTR curve, and the honesty rules — never show a number the engine
cannot stand behind, never tune a threshold to make a rule fire.
