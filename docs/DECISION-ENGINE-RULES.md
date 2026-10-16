# Decision engine: every rule, what triggers it, and the data it reads

Written from the code on `main` (October 2026). File names are given so each claim can be checked.
Where a number is a threshold it is the value in the code today; none are per-client settings
(`thresholds = {}` in `monthly_run.build_record`).

## 1. How a run works

1. **When.** The worker runs on the 5th of the month (`monthly_run_day`, 12:00 UTC) for the **previous, finished
   month** and saves one record per client (`monthly_records`). The page renders the saved record; it never recomputes.
   Admins can re-run a finished month; the current month is refused.
2. **Triage (Decision 1).** Three branches are tested in order **Visibility → Traffic → Leads**. A branch *fails* if any
   of its tests fails, is *blocked* if none failed but one had no input, and *passes* only if every test had data and passed.
3. **Constraint.** The first failing branch in that order is "this month's constraint". Blocked branches are skipped.
   If nothing fails the constraint is `visibility_expansion`. Overrides: a relaunch/migration annotation in the last
   180 days forces Visibility; stale data (>7 days) withholds the whole run; an admin can override by hand.
4. **Candidates (Decision 2).** Visibility actions come from **keyword targets** (the keyword map), scored and ranked.
   Traffic and Leads actions come from **pages** (Search Console + GA4 + crawl). Update and new-content pools are separate.
5. **Slots (Decision 3).** Growth slots by plan: Launch/Legacy 1, Lift 3, Lead 5, Enterprise 5+. They fill from the
   constraint branch first, then spill to other **failing** branches only. A passing or blocked branch's actions can
   never take a slot ("Leads passes, so it cannot take a slot"). One action per URL per month. Unfilled slots stay empty.
6. **Retainer pools** (outside the growth slots): *updates* (refresh pages losing ground) and *new content*
   (pages for terms/queries with no page), against the plan's allowances.

## 2. Triage tests (`decisions/triage.py`, inputs in `services/triage_signals.py`)

Managed channels for GA4 = organic search, AI referral, direct/unattributed, referral.

| Test | Question | Value | Pass line | Data read | Blocked when |
|---|---|---|---|---|---|
| **V1** | Are priority terms ranking? | share of **priority-marked, mapped** tracked terms in top 10 | ≥ 30% | `keyword_targets` (confirmed, priority) joined to `facts_ser_keywords.current_position` | no term is marked priority |
| **V2** | Is SE Ranking visibility falling? | % lost over 90 days | ≤ 15% | `facts_ser_site_summary.visibility_percent` now vs ~90 days ago | no history |
| **V3** | Are impressions falling? | % lost, last 28 days vs the 28 before | ≤ 15% | `facts_gsc_daily.impressions` | not enough GSC history |
| **V4** | Can target pages be found? | declared pages **that have a term mapped** and no mapped term in the top 20 | = 0 | declared = priority targets' pages + `client_conversion_pages`; reach = any confirmed mapping to that page ranking ≤ 20 | no declared pages, or none has a term mapped *(fixed in PR 24; before, an empty map failed this)* |
| **V5** | Does the brand appear in AI answers? | % of tracked prompts mentioning the brand | ≥ 20% | `facts_ser_ai_tracker_stats`, `facts_ser_ai_checks` | no tracked prompts |
| **V5b** | AI share of voice falling? | % lost over 90 days | ≤ 25% | AI tracker stats | only runs if data exists |
| **T1** | Are rankings earning the clicks they should? | clicks missed ÷ clicks earned | ≤ 20% | `facts_gsc_pages` last 30 days, per page: expected = CTR-curve(avg position) × impressions; missed = max(0, expected − actual), summed over **all pages** | no clicks |
| **T2** | Impressions up, visits not? | impressions change − sessions change, only if impressions +10% and sessions ≤ 0 | 0 | GSC daily vs GA4 managed sessions, 28 vs prior 28 | no comparison data |
| **T3** | Is engagement healthy? | engaged-session rate | ≥ 50% | `facts_ga4_traffic.engaged_sessions` (28 days) | no engagement data |
| **T3b** | Engagement vs its own history | rate ÷ 6-month rate | ≥ 80% | same, 182 days | only if both exist |
| **L1** | Leads on pace? | leads to date ÷ goal pro-rated to today | ≥ 80% | `facts_ga4_events` for active lead conversion events (managed channels); `clients.monthly_lead_goal` | no conversion events, or no goal |
| **L2** | Lead rate vs baseline? | lead rate ÷ client's baseline lead rate | ≥ 80% | leads ÷ managed sessions this month; `clients.baseline_lead_rate_pct` | no baseline (locked baseline sets it) |
| **L3** | Do landing pages route onward? | share of sessions landing on pages with no route onward | ≤ 50% | GA4 landing sessions, crawl internal links, confirmed funnel stages, declared conversion pages; needs ≥ 60% of traffic on staged pages | too little staged traffic / no conversion pages |

CTR curve: `decisions/data/organic_ctr_benchmark_2026_jul_us.csv` (position 1 ≈ 20.0%, 2 ≈ 10.4%, 3 ≈ 3.9%, 4 ≈ 1.7%, 10 ≈ 0.6%, 20 ≈ 0.3%).

## 3. Scoring visibility candidates (`decisions/targets.py`)

Only keywords with a **confirmed** row in `keyword_targets` are candidates. Tracked keywords with no row do not exist to the engine.

`score = volume × intent × group × reach × fit` (zero on any factor removes the candidate)

- **volume**: search volume (`facts_ser_keyword_metrics`).
- **intent**: 1.0 for commercial/conversion target pages (or unknown), 0.4 informational. Read from the declared page's type.
- **group**: 1.5 if the target is marked priority, else 1.0.
- **reach** (position, difficulty): top 3 → 0.1; 4–10 → 1.0; 11–20 → 0.8; 21–30 → 0.5; 31–100 → 0.15; unranked → 0.15 (unknown difficulty) or 0.3 × (1 − difficulty/100).
- **fit**: 1.0 if the ranking URL is the mapped URL (compared ignoring http/https, www, trailing slash), 0.5 if a different URL ranks (→ V-6), 0.7 if no page is mapped.

This is why one term wins a slot over another: higher volume, priority flag, nearer page one, and a commercial page — multiplied.

## 4. Visibility actions (first that fires wins, in this order; `decisions/catalog.py`)

All need the target's page to have been **read by the crawl** (crawl row for the mapped URL, following a redirect row to the page it lands on). An unread page gets no V action (except V-6).

| ID | Action | Fires when | Data |
|---|---|---|---|
| **V-6** | Settle which page owns the term | a different URL than the mapped one ranks for the term | `facts_ser_keywords.ranking_url` vs `keyword_targets.target_url` |
| **V-1** | Put the term in the title / a heading | primary term missing from the **title** or from **every heading** (phrase match, case-insensitive). Meta description is no longer checked | crawl title; crawl sections (headings) |
| **V-8** | Give a secondary term a section | secondary term in no heading | crawl sections |
| **V-2** | Add an answer block | term starts with a question word and no FAQ question matches | crawl `faq_questions` |
| **V-7** | Mark up the FAQ | page has an FAQ-headed section and no FAQPage schema | crawl sections, schema rows |
| **V-5** | Add something liftable | SERP carries an extractive feature (featured snippet / AI overview / PAA…), a heading asks the term, and nothing under it is a table/list/stat | SERP features (DataForSEO), crawl section flags |
| **V-3** | Add entity markup | page has no `about`/`mentions` schema | `facts_crawl_page_schema` |
| **V-4** | Add internal links | editorial inbound links < site median | crawl inbound editorial links |

V-1/V-2/V-3/V-4/V-8 stay silent when the page was not read as a 2xx or headings were not captured (unknown ≠ empty).

## 5. Traffic actions (page-level; `decisions/catalog.py`, pages ranked by missed clicks then sessions)

| ID | Action | Fires when | Data |
|---|---|---|---|
| **T-1** | Rewrite title/meta | page **average position ≤ 3**, ≥ 100 impressions, ≥ 1 missed click, top query is not the brand | GSC page + curve |
| **T-2** | Match the SERP format | page position ≤ 10, top query has a winnable SERP feature the client does not hold, SERP pulled | GSC, SERP features |
| **T-3** | Rewrite the opening | ≥ 50 sessions and engagement below the site's own median | GA4 landing engagement |

**There is no traffic action for a page ranking 4 or lower that earns fewer clicks than its position "should".** Those clicks count
toward T1 and are reached by nothing in this list.

## 6. Leads actions (page-level; every one needs a **confirmed funnel stage** for the page)

| ID | Action | Fires when |
|---|---|---|
| **L-1** | Add an in-content route to the next step | stage known and not bottom-of-funnel, page links in content to no declared conversion page, a matching offer exists, page is not itself a conversion page |
| **L-2** | Add a call to action | stage known, crawl found 0 forms/CTAs |
| **L-3** | Point at an offer the reader is ready for | page has routes out, none of which fit its stage, a fitting offer exists |

Data: crawl internal links + `conversion_elements`, `client_page_stages`, `client_conversion_pages`, GA4 sessions.

## 7. Update actions (retainer pool; pages losing ground; `decisions/update_catalog.py`)

First that fires wins, in this order. A page must have drawn ≥ 100 impressions in the prior 28 days.

| ID | Action | Fires when |
|---|---|---|
| **U-2** | Win back a lost position | top lost query was ≤ position 3, now > 3 and dropped ≥ 2 places, not a brand query |
| **U-3** | Answer the question it draws | decaying page, the lost query is a question, no heading/FAQ answers it |
| **U-6** | Fix broken structured data | schema block present but does not parse, ≥ 100 impressions |
| **U-5** | Settle which page owns a term | another page of the site also draws a real share (≥ 30%, ≥ 100 impressions) of the same query |
| **U-1** | Refresh the page | decaying (impressions down ≥ 25% and ranking not improved) and not a stub (< 250 words) |
| **U-4** | Link it from pages that should | ≥ 100 impressions, position within reach, < 3 editorial inbound links, donor pages found |

## 8. New-content actions (retainer pool; `decisions/content_gaps.py`)

Needs a crawl of ≥ 10 indexable pages, otherwise blocked.

- **Tracked-term gap**: a tracked keyword with no mapping (or recorded as "no page"), not a brand query, not already ranking with a URL,
  with volume ≥ 50 and difficulty known, where no crawled page's title+URL+headings covers ≥ 60% of its words.
- **Demand gap**: a Search Console query (last 90 days) with ≥ 90 impressions, no page ranking ≤ 10 for it, no page covering it,
  priced by DataForSEO (top 25); competitor keywords add suggestions.

## 9. Things in this design that can mislead (my reading; for your decision)

1. **The keyword map is the engine's whole view of Visibility.** Unmapped tracked terms are not candidates and are not counted in V1.
   A client with a near-empty map gets Visibility actions for nothing, and V1/V4 judge a tiny sample. (V4's empty-map failure is fixed in PR 24; V1 on a tiny sample is not.)
2. **Visibility always outranks Traffic and Leads.** Any single failing Visibility test makes it the constraint, so a setup gap can
   crowd out a real traffic problem (Corvant, September 2026).
3. **T1 is a ratio on tiny volume.** 58 missed vs 72 earned fails the same as 5,800 vs 7,200, and the curve's 20% at position 1 can be
   wrong for navigational pages.
4. **T-1 only reaches the top three.** Missed clicks on pages ranking 4+ have no action.
5. **A branch only passes if every test had data.** Missing data blocks; blocked branches cannot take slots and are otherwise treated like a pass
   when choosing the constraint.
6. **L-1 fires for every page with no routed link** (41 pages on Corvant), and its evidence line says `conversion_elements = 0`, which is not its trigger.
7. **Unknown vs empty** was the V-1 bug; PR 22 fixed V-1/V-2/V-3/V-4/V-8 and V-6's URL comparison. The admin "Decision engine inputs" report lists affected pages.
8. **L2** is blocked until a baseline is locked (it reads `baseline_lead_rate_pct`), which the baseline reset cleared for every client.
