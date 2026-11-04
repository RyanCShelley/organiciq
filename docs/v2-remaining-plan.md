# Organic IQ v2: the rest of the plan (DRAFT for review)

Status: draft, organised around the navigation and order Ryan gave on 2026-11-02. Nothing here is built. Items marked
**OPEN** need an answer and are not assumed. Sizes are my rough estimates: S is 1 to 2 days, M is 3 to 5, L is 1 to 2 weeks.

Builds on `docs/rebuild-plan.md` (decisions, original phases) and replaces its phase order for what is left. Rule codes
(A-1, S-4) never appear in anything the team sees.

## 1. Navigation (Ryan's structure)

| Group | Screen | State |
|---|---|---|
| **OrganicIQ Analytics** | Monthly review | built |
| | Business Intelligence: deeper, ad hoc reporting, with an LLM to question the data | to build (replaces the Dashboard placeholder) |
| | Decision engine | built |
| **Visibility** | Search visibility report: Search Console, Bing and SE Ranking compared together | to build |
| | LLM visibility | built |
| **Dual optimization** (search and AI) | Site health: SEO crawler and GEO crawler | to build |
| | Schema and knowledge graph: analyse the current site, suggest optimizations | to build |
| | CTR optimizer | to build |
| | Inlink suggester | to build |
| **Content engine** | Content gaps | to build |
| | Content refreshes | to build |

**Decided (A, 2026-11-03).** Focus stays inside Monthly review. Watchlist stays in the client settings, with the other settings.
Admin sits at the bottom left, as in v1 (the current sidebar placement is right). The content calendar goes under Content
engine. The change log goes under Business Intelligence, on the analytics side.

## 2. One pattern for every screen

The new screens must feel like one tool. Every screen is built from the same parts, in the same order:

1. **Header strip.** Client, "data through" per source, month picker (later: quarter, custom range, year over year).
2. **Headline numbers.** Four at most, each with its change and what it is compared with.
3. **A filterable table.** Filter chips, one line per thing, no sideways scroll.
4. **Click a row for the evidence.** What the data says, where it came from, how old it is.
5. **One action: send to the plan.** A finding on any screen becomes a candidate in the Decision engine, so Site health,
   CTR, links, schema and content findings use the same plan, monthly allowance, Teamwork and 28-day results loop. There is
   no second task system.

Everywhere: something running shows a spinner and progress (built); empty states say what to connect or do next; numbers say
what they are compared with; errors appear next to what caused them; no rule codes.

## 3. The screens, in build order

Order follows your navigation top to bottom, skipping what is built. The end-to-end run on Absolutely Natural (section 5)
comes first.

### 3.1 Business Intelligence

- **Answers:** why did a number move, and any question the fixed screens do not answer.
- **Two parts.** (1) **Drill-downs** behind the Monthly review's numbers: landing pages by channel with visits, key actions
  and conversion rate; conversion sources and engagement; keyword position at month start against month end; time frames
  (quarter, custom range, year over year); annotations drawn on the charts. Reuses `dashboard.py` and
  `dashboard_exploration.py` (dated, source-backed drill-downs) and `monthly_review.py`. (2) **Ask the data:** a chat box that
  answers questions about this client's data with the numbers and where they came from.
- **Ask the data builds on the Copilot module** (`app/copilot`: chat, tools, playbook), which is already planned for every
  screen. **OPEN B (compared 2026-11-03; recommendation: the Claude 5 family, see the results note below; Ryan to choose):** which model answers (the Copilot gateway speaks the OpenAI-compatible protocol and is not configured;
  the four AI platform keys already on the install are another option), and the safety rules: read-only, this client only,
  every figure cited to its table, a monthly cost cap. You linked an article on the best LLM for data analysis; I have not
  read it, so tell me if it should decide the model.
- **Size:** M for the drill-downs, M for Ask the data.

### 3.2 Search visibility report

- **Answers:** where does the client show up in Google, Bing and SE Ranking for the terms that matter, and do the sources
  agree.
- **Reuses:** watchlist, Search Console and SE Ranking facts, Bing query stats (weekly), `serp_features.py`, the Monthly
  review's visibility section.
- **To build:** the three sources compared side by side per term (position, impressions, clicks) with disagreements flagged;
  ranking trends per bucket and term; position distribution (1 to 3, 4 to 10, 11 to 20, beyond); winners and losers; the
  Google algorithm overlay (Google's incident feed drawn on the trend; check `incident_signals.py` first so there is one feed).
- **Layout:** headline (terms showing, on page one, average position, clicks); bucket selector; one table with a column per
  source and a sparkline; click a term for its pages, the competitors in the top 10 and SERP features.
- **Size:** M, plus S for the overlay. **Depends on:** Bing and SE Ranking pulled for the client (done for Absolutely Natural).

### 3.3 Site health (SEO crawler and GEO crawler)

- **Answers:** is the site technically sound for search, and ready for AI answers, and what changed since last month.
- **Reuses:** the first-party crawl (pages, issues, schema, internal links, redirects, robots), the Site crawl API, and from
  GEO Grader the retrieval-readiness signals (schema, FAQ, entity clarity, AI-crawler access).
- **To build:** **two scores, each locked monthly:** SEO health (titles, indexation, structured data, 301s, 404s, redirect
  chains, broken internal links) and GEO readiness (what the site offers an AI answer). Weights written down and shown. New and
  fixed issues since last month; issues grouped by what to do, not by crawler label.
- **Layout:** two headline scores with their change; issue groups ordered by pages affected; click a group for the pages and
  the fix; Send to plan.
- **Decided (C).** Ryan already has a scoring logic in his SEO crawler and GEO tool. We walk through those two tools and port
  their logic (checks, weights, thresholds) rather than proposing new ones. The GEO tool is the Railway project "GEO Grading Tool" (geo-grader-frontend and geo-grader-backend); its code is the
  GitHub repo RyanCShelley/geo-grader, with a local copy on Ryan's Desktop. The SEO crawler score is built from this tool's own crawler.
  GEO logic to port, from `backend/app/services/retrievability.py` (the "retrievability" score, 0 to 100): schema markup 15%
  (JSON-LD present 40, plus 10 for each of organization, local business, service, FAQ page, product, professional service; microdata
  20), FAQ structure 10% (FAQ page markup 50, FAQ headings 25, details elements up to 25), entity clarity 10% (title 25, description
  25, about link 15, contact link 10, phone 15, street address 10), AI-crawler access 10% (100 minus 20 for each of GPTBot, CCBot,
  Google-Extended, ChatGPT-User, Anthropic disallowed in robots.txt), citation 20%, content depth 15%, knowledge graph 10%, source
  attribution 10% (these last four read the AI answers). The grader reads one page; ours has every crawled page, so the first four can
  be scored site-wide and the last four come from LLM visibility runs.
- **Size:** M to L. **Caution:** the crawl stops at its page limit (500 by default) and is slow on Shopify because the host
  rate-limits. A score on a partial crawl must say so.

### 3.4 Schema and knowledge graph

- **Answers:** what structured data does the site declare, what should it, and does the brand read as one clear entity.
- **Reuses:** crawl schema blocks (`/schema`, `schema_types.py`) and Topic Hub's schema audit.
- **To build:** current schema by page type; missing or wrong types by page intent; entity checks (the brand's name, same-as
  links, organisation and product markup, consistency across pages); suggested markup the team can paste. Reads the live
  page; the suggestion is a draft a person checks.
- **Size:** M. **Depends on:** Site health's crawl.

### 3.5 CTR optimizer

- **Answers:** which pages and searches show a lot and get clicked too little for their position.
- **Reuses:** `ctr_diagnostic.py` (industry CTR reference), the Visibility candidate bands, Bing impressions and clicks.
- **To build:** searches and pages with click-through against the expected rate at their position, ranked by extra clicks if
  fixed; a site clickability score tracked monthly; Google and Bing together; before and after on title or description
  changes (tied to the plan's results loop).
- **Layout:** headline (score, extra clicks available, pages below benchmark); the ranked table; click a row for the current
  title and description, what it ranks for, and Send to plan.
- **OPEN D.** You answered "see other notes" on whether CTR is its own screen or part of the engine. Your navigation lists it
  as its own screen, so I have planned it that way. If your other notes say more, send them.
- **Size:** S to M.

### 3.6 Inlink suggester

- **Answers:** which page should link to which.
- **Reuses:** `link_gaps.py` (two pages ranking for one query), `crawl_link_facts.py` (links to a page, in-content, navigation
  and template links separated), Topic Hub's link recommendations.
- **To build:** suggestions of the form "link from this page to that page with this anchor", ranked by what the target gains;
  orphan and thin-link pages; cannibalization pairs; Send to plan.
- **Size:** M.

### 3.7 Content gaps

- **Answers:** what demand does the site have no page for.
- **Reuses:** `content_gap_signals.py` (watchlist terms with no page), `demand_gaps.py` (searches shown for with no page about
  them), competitor top-ten terms.
- **To build:** a ranked list of gaps with the evidence (volume, competitors ranking, the nearest existing page), grouped by
  watchlist bucket; Send to plan as a "new page" growth action; match against the content calendar if it is built.
- **Size:** M.

### 3.8 Content refreshes

- **Answers:** which existing pages are decaying and worth updating, and what to change.
- **Reuses:** the Traffic candidates (year-over-year and slow-bleed tests), annotations, the diagnosis.
- **To build:** lifecycle labels per page (new, growing, plateau, decaying); a ranked refresh list with the reason and what
  changed since the page last moved; Send to plan; the change log (annotations) shows what was done and when.
- **Size:** M. **Note:** this overlaps the engine's Traffic tab; the difference is intent. The engine answers "what dropped
  this month"; Refreshes answers "what should we update next, dropped or not".

### Ask-the-data model comparison (2026-11-03)

Twelve of Ryan's questions, one read-only SQL tool over Absolutely Natural's data, eight models. Fable 5.1, Opus 5.5, Sonnet 5.5 and
Haiku 5.5 queried several times, checked the data's gaps and cited tables and periods. GPT-4o and Gemini answered after one query or none,
and GPT-4o-mini invented numbers (an average engaged duration the data does not hold, and the wrong years). Data gaps the tool must
show the user: no session duration or time on page in GA4, the SE Ranking competitor tables are empty for this client, and most
purchases arrive as "other" or "direct_unattributed".

## 4. Build order

| # | Work | Size |
|---|---|---|
| 0 | End-to-end run on Absolutely Natural (section 5) | in progress |
| 1 | Business Intelligence: drill-downs, then Ask the data | M + M |
| 2 | Search visibility report, with the algorithm overlay | M + S |
| 3 | Site health (SEO and GEO scores) | M to L |
| 4 | Schema and knowledge graph | M |
| 5 | CTR optimizer | S to M |
| 6 | Inlink suggester | M |
| 7 | Content gaps | M |
| 8 | Content refreshes | M |

Dependencies that could force a swap: Schema needs Site health's crawl; CTR's score history needs Search visibility's trend
data; Content gaps use link and query data from the screens before it. If a swap is needed, I will say so before doing it.

## 5. End-to-end acceptance on one client (Absolutely Natural)

The tool is "working end to end" when a person has done each step on real data and the result is right:

1. Connect all five sources and **Pull data**; every source shows done and the Data through strip is current.
2. Save the LLM brand and competitors; **Suggest prompts**; run LLM visibility; the review shows the AI numbers.
3. Open the Monthly review; check three numbers by hand against Search Console and GA4.
4. Choose a focus and a bucket; open the Decision engine; diagnose a page; confirm a growth action.
5. Send it to Teamwork; the task appears with the assignee and steps; mark it shipped; the baseline is recorded.
6. A scheduled sync runs overnight without help; nothing is stuck in the morning.
7. 28 days later the results loop reports before and after.

Steps 1 to 5 can be done this week; 6 needs a night; 7 needs the month. Anything that fails goes on a list and is fixed
before the next screen starts.

## 6. Also still open (not screens)

- Copilot panel on every v2 screen (decided earlier, not built); Ask the data (3.1) is the same capability.
- Topic Hub keyword-map matching port.
- Client-facing access (roles exist): every screen is read-only friendly; what a client sees is signed off later.
- Cutover: remove the old tool's Watch List and `watch_targets`, drop `.net` from the sign-in domain list, open the pull
  request to main, rotate the OpenAI and Perplexity keys that were printed once by mistake.
- Docs: `DEPLOY.md` still lists a variable v2 does not need and does not say the API address must start with `https://`.
