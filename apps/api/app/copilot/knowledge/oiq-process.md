# Organic IQ process

Condensed from `docs/decision-engine/docs/decision-engine-spec.md`. The spec is
the source of truth; update this file when it changes. It lives here because
the API image is built from `apps/api` and cannot see `docs/`.

## How a month works

Each month the engine names one primary constraint (Visibility, Traffic or
Leads), picks the highest-value targets inside it, and prescribes as many growth
actions as the client's plan allows, each under an hour. Baseline work runs
every month regardless: new content, decaying-content updates, technical SEO,
on-page review of main navigation pages, Google Business Profile upkeep,
content link promotion, data analysis. The engine only decides where the next
marginal hour goes.

## Principles

- Upstream first: Visibility gates Traffic, Traffic gates Leads. A downstream
  branch becomes the constraint only when every branch above it passes.
- One constraint per month. It gets the slots first; unfilled slots go to the
  next failing branch, never to a branch that passes or is blocked.
- The plan sets the action count: Launch and legacy 1, Lift 3, Lead 5,
  Enterprise 5 or more. Never exceed it, never pad it.
- Managed channels only: organic_search and ai_referral sessions.
- No data, no rule. If an input is missing the rule does not fire and the
  output names the gap. Never guess from URL fragments.
- Every action cites its evidence and carries a metric and a check date. The
  same action is not prescribed on the same URL again before its check date.

## Choosing the constraint

A branch fails if any test fails, is blocked if a test lacks its input and none
fails, and passes otherwise. A relaunch, migration or domain change logged in
annotations within 180 days forces Visibility. A constraint holds at least two
months and releases early only when every test clears its pass line by 10%.
Incidents (zero lead events for 14 days after a history of leads, a drop of more
than 20% in indexable pages, a site-wide technical fault) go to the technical
baseline; they use no slot and do not change the constraint.

Visibility tests: V1 priority-term coverage (fails under 30% of priority
keywords in the top 10); V2 visibility trend (falls more than 15% over 90 days);
V3 impression trend (managed impressions fall more than 15%, 28 days vs prior
28); V4 priority-page reach (a priority page has no term in the top 20); V5 AI
answer presence (brand in under 20% of tracked prompts, or AI share of voice
falls more than 25% over 90 days).

Traffic tests: T1 missed clicks (over 20% of actual organic clicks); T2
divergence (impressions up over 10% while managed sessions are flat or down);
T3 engagement quality (engaged-session rate under 50%, or under 80% of the
client's 6-month median).

Lead tests: L1 goal pace (month-to-date under 80% of the pro-rated goal); L2
lead rate (under 80% of baseline); L3 next-step flow (over 50% of managed
sessions land on top-of-funnel pages with no in-content link to a mid or bottom
funnel page). No conversion definitions means Leads is blocked, never passed.

If everything passes, the constraint is Visibility expansion.

## Choosing targets

Visibility targets are keyword-page pairs scored volume x intent x group x reach
x fit. Traffic targets are pages with at least 200 managed impressions in 28
days (CTR gaps, audience mismatch; bot-like pages are dropped). Lead targets are
landing pages with at least 100 managed sessions in 28 days (low lead rate,
dead ends, no CTA); smaller ones are a last resort, flagged small_sample, and
lower confidence.

## Action catalog

Within a branch, the first action whose trigger fires for a target is used.

- V-1 place the target term in high-value spots (title, an H2, first 100 words).
  Measured by term position at 28 days.
- V-2 add an answer block or FAQ with FAQPage markup (40-60 word direct answer
  under a question heading). Measured by brand mention or citation at 30 days.
- V-3 add entity markup (about/mentions, Wikidata sameAs). 45 days.
- V-4 add internal links to the target (2-3 in-content links with term or
  variant anchors). 28 days.
- V-5 add an extractable structure (table, bullet summary, stat block) where the
  SERP shows an AI Overview or snippet. 30 days.
- V-6 raise a re-homing ticket when a term ranks on a non-target URL or two or
  more URLs. Decision only.
- T-1 rewrite title and meta description for pages in the top 3 with missed
  clicks (title 60 characters or fewer). CTR vs expected at 28 days.
- T-2 match the SERP format. 30 days.
- T-3 realign the page to the audience. Engaged rate at 28 days.
- L-1 route readers to the next step. Leads at 30 days.
- L-2 add or move a call to action. Lead rate at 30 days.
- L-3 match the offer to the topic. Lead rate at 45 days.

V-2, V-3 and V-5 are the GEO layer.

## Two pools

The Decision Engine is the growth plan (outside the retainer). Content Opp is
the retainer plan (inside the monthly fee): refresh updates and new content,
with their own allowances by tier (Launch 1/1, Lift 2/2, Lead 3/3 for
content/refresh). Both are ranked, slotted, assignable, sent to Teamwork and
judged by the results loop.

## Confidence and suppression

High confidence means every input is present and fresh; medium means a fallback
was used; low means a core input is missing or questionable and the page leads
with "check before you assign". If Search Console or GA4 data is more than 7
days stale the client is Withheld and no actions are produced. URLs in the
refresh queue, non-indexable URLs, redirects and soft 404s are skipped and sent
to the technical baseline. One action per URL per month.
