# Organic IQ v2: the rest of the plan (DRAFT for review)

Status: draft. Nothing here is built. Items marked **DECIDE** need an answer from Ryan and are not assumed. Sizes are rough
and are my estimates: S is 1 to 2 days, M is 3 to 5, L is 1 to 2 weeks.

Builds on `docs/rebuild-plan.md` (decisions, phases) and replaces its phase order for what is left. Rule codes (A-1, S-4)
never appear in anything the team sees.

## 1. Where we are

Built and in use: Monthly review (the client's home), Decision engine (Visibility, Traffic and Leads candidates, diagnosis,
growth actions, Teamwork, results after 28 days), LLM visibility (four platforms, brand check, prompt suggestions),
Watchlist, Focus, Settings (connections, conversions, baseline, competitors, content sources, team), Admin (add, remove,
pull data) and the scheduled data pulls (Search Console, GA4, SE Ranking daily; crawl and Bing weekly; LLM every 28 days).

Greyed in the sidebar and still to build: **Dashboard, Site Health, Search Visibility, CTR Optimizer, Content Hub**. The
algorithm overlay (Google's incident feed on the charts) is also left.

Before any of it: the **end-to-end run on Absolutely Natural** (section 7). New screens come after that is trusted.

## 2. One pattern for every screen

The five screens should feel like one tool, not five. Every screen is built from the same parts, in the same order:

1. **Header strip.** Client, "data through" dates per source, month picker (later: quarter, custom range, year over year).
2. **Headline numbers.** Four at most, each with its change and what it is compared with.
3. **A table you can filter.** Filter chips, one line per thing, no sideways scroll, no hunting for the next step.
4. **Click a row for the evidence.** What the data says, where it came from, how old it is.
5. **One action: send to the plan.** Any finding on any screen can become a candidate in the Decision engine, so Site
   Health, CTR and Content findings flow through the same plan, allowance, Teamwork and 28-day results loop. No second
   task system.

Rules that apply everywhere: something running shows a spinner and progress (built); no rule codes; empty states say what
to connect or do next; numbers say what they are compared with; every error is shown next to the thing that caused it.

## 3. Sidebar

Today the sidebar is a flat list. Proposed, grouped by what the person is doing:

| Group | Screens |
|---|---|
| **Review** | Monthly review, Dashboard (the explorer behind it) |
| **Work** | Focus, Decision engine (with the plan) |
| **Measure** | Search visibility, CTR optimizer, LLM visibility, Site health |
| **Content** | Content hub, Watchlist |
| **Setup** | Settings |

Placeholders disappear from the sidebar once their screen exists; a screen that is not ready is not shown to the team.
**DECIDE 1:** is this grouping right, or do you want it flat?

## 4. The screens

### 4.1 Dashboard (the explorer behind the Monthly review)

The Monthly review already does the "monthly report" job: results, traffic, search, channels, top pages, visibility, a plain
summary. **DECIDE 2:** keep one place and make Dashboard its drill-down, or keep them as two screens? I recommend one:
Monthly review stays the home, and each number on it opens the Dashboard view for that number.

- **Answers:** why did this number move, and which pages, channels and terms moved it.
- **Reuses:** `dashboard.py`, `dashboard_exploration.py` (dated, source-backed drill-downs), `monthly_review.py`.
- **To build:** landing pages by channel (visits, key actions, conversion rate); conversion sources and engagement;
  keyword position at month start against month end; recap and wins; time frames (quarter, custom range, year over year);
  annotations drawn on the charts (the annotation tables already exist).
- **Layout:** the headline strip, then one tab per question (Channels, Pages, Conversions, Keywords), each a filterable
  table with a small trend chart above it.
- **Size:** M. **Depends on:** nothing new.

### 4.2 Search visibility

- **Answers:** where does the client show up in Google and Bing for the terms that matter, and is that moving.
- **Reuses:** watchlist, Search Console and SE Ranking facts, Bing query stats (weekly), `serp_features.py`, the monthly
  review's visibility section (term table with Google, Bing and AI columns).
- **To build:** ranking trends per bucket and term (position over time, month start against end); position distribution
  (how many terms in 1 to 3, 4 to 10, 11 to 20, beyond); winners and losers; Google and Bing side by side; the algorithm
  overlay on the trend.
- **Layout:** headline (terms showing, on page one, average position, clicks); a bucket selector; the term table with a
  sparkline per row; click a term for its pages, competitors in the top 10, and SERP features.
- **Size:** M. **Depends on:** Bing data pulled for the client (done for Absolutely Natural).
- **Note:** this screen and the monthly review's visibility section overlap. The review keeps the one-screen summary; this
  screen is where you go for the trends.

### 4.3 CTR optimizer

- **Answers:** which pages and searches show up a lot and get clicked too little for their position.
- **Reuses:** `ctr_diagnostic.py` (industry CTR reference), the Visibility candidate bands, Bing impressions and clicks.
- **To build:** a table of searches and pages with click-through against the expected rate at that position, ranked by
  extra clicks if fixed; a site-level clickability score tracked monthly; Google and Bing together; a before-and-after on
  title or description changes (tied to the plan's results loop).
- **Layout:** headline (clickability score, extra clicks available, pages below benchmark); the ranked table; click a row to
  see the current title and description, what the page ranks for, and **Send to plan** for a title and description action.
- **DECIDE 3:** should CTR be its own screen, or a lens inside the Decision engine's Visibility tab? The engine already
  ranks by expected extra clicks, so most of the work exists. I recommend a small screen for the score and trend, with the
  actions living in the engine.
- **Size:** S to M. **Depends on:** Search visibility's trend data for the score history.

### 4.4 Site health

- **Answers:** is the site technically in good shape, and what changed since last month.
- **Reuses:** the first-party crawl (pages, issues, schema, internal links, redirects, robots), the Site crawl API
  (`/pages`, `/schema`), `crawl_link_facts.py`, `link_gaps.py`.
- **To build:** a **health score locked each month** (titles, indexation, structured data, 301s, 404s, redirect chains,
  broken internal links) with the weights written down and shown; the schema check by page intent; new and fixed issues
  since last month; issues grouped by what to do, not by what the crawler calls them.
- **Layout:** headline (score, change, new issues, fixed); issue groups as a list ordered by pages affected; click a group
  for the pages and the fix; **Send to plan**.
- **DECIDE 4:** how the score is weighted. I will propose weights; you approve them, as with the engine thresholds.
- **Size:** M to L. **Depends on:** a full crawl. Note the crawl stops at the page limit (500 by default) and was slow on
  Shopify because the host rate-limits; a score on a partial crawl has to say so.

### 4.5 Content hub

- **Answers:** what has been published, what is missing, what should be updated, and what is competing with itself.
- **Reuses:** blog feeds (stored per client), `content_gap_signals.py`, `demand_gaps.py`, `link_gaps.py`, the keyword map and
  `automatic_keyword_map.py`, annotations.
- **To build:** the post history from the feed (every entry stored permanently, backfilled from the crawl); the content
  calendar from the account sheet; lifecycle labels per page (new, growing, plateau, decaying); gap analysis against watchlist
  subtopics; cannibalization (two pages ranking for one query); internal-link recommendations; the change log (annotations).
  Port from Topic Hub: clusters, cannibalization, link recommendations.
- **Layout:** tabs for Calendar, Pages (lifecycle), Gaps, Links. Each row has Send to plan.
- **DECIDE 5:** content calendar source. The plan says it is imported from the account sheet; confirm the sheet format
  before building, starting with Absolutely Natural.
- **Size:** L. **Depends on:** Search visibility (query data per page) and Site health (links).

### 4.6 Algorithm overlay

Google's Search Status Dashboard feed (`incidents.json`) drawn as bands on the trend charts in Dashboard and Search
visibility. To verify first: what `incident_signals.py` already reads, so we do not build a second feed. **Size:** S.

## 5. Order, and why

| # | Work | Why here | Size |
|---|---|---|---|
| 0 | End-to-end run on Absolutely Natural (section 7) | Nothing new is trusted until the engine, review and results loop are | in progress |
| 1 | Search visibility, then the algorithm overlay | The data is already in; it feeds CTR, Dashboard and Content | M + S |
| 2 | CTR optimizer | Mostly the engine's own ranking, shown as a score and a trend | S to M |
| 3 | Dashboard | Drill-downs behind numbers the review already shows | M |
| 4 | Site health | Largest unknown is the weighting; the crawl is ready | M to L |
| 5 | Content hub | Largest; needs query data and links from the earlier screens | L |

This is a recommendation. **DECIDE 6:** the order, if you want Site health or Content earlier for a client reason.

## 6. Also still open (not screens)

- Copilot panel on every v2 screen (decided earlier, not built).
- Topic Hub mapping port (the keyword map's matching logic).
- Client-facing access (roles exist): every screen above is read-only friendly, but sign-off on what a client sees is later.
- Cutover: remove the old tool's Watch List and `watch_targets`, drop `.net` from the sign-in domain list, open the pull
  request to main, rotate the OpenAI and Perplexity keys that were printed once by mistake.
- Docs: `DEPLOY.md` still lists a variable v2 does not need and does not say the API address must start with `https://`.

## 7. End-to-end acceptance on one client (Absolutely Natural)

The tool is "working end to end" when each step below has been done by a person on real data and the result is right:

1. Connect all five sources and **Pull data**; every source shows done and the Data through strip is current.
2. Save the LLM brand and competitors; **Suggest prompts**; run LLM visibility; the review shows the AI numbers.
3. Open the Monthly review; check three numbers by hand against Search Console and GA4.
4. Choose a focus and a bucket; open the Decision engine; diagnose a page; confirm a growth action.
5. Send it to Teamwork; the task appears with the assignee and steps; mark it shipped; the baseline is recorded.
6. A scheduled sync runs overnight without help; nothing is stuck in the morning.
7. 28 days later the results loop reports before and after.

Steps 1 to 5 can be done this week; 6 needs a night; 7 needs the month. Anything that fails goes on a list and is fixed
before the next screen starts.
