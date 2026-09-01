# Organic IQ

SMA Marketing's operating system for predictable organic growth.

**Status:** Phase 7 — 90-day validation (SMA Marketing test client)

## Stack

- **Web:** Next.js 15 + TypeScript + Tailwind + Auth.js (Google Workspace)
- **API:** Python FastAPI + SQLAlchemy 2 + Alembic
- **DB / jobs:** PostgreSQL 16; durable sync jobs via dedicated worker (`FOR UPDATE SKIP LOCKED`)
- **Hosting target:** Railway (Postgres + API + worker; web on Railway or Vercel)

## Repository layout

```
apps/web     Next.js app
apps/api     FastAPI + worker
docker-compose.yml
```

## Local development

Requires **Python 3.13** for the API (3.14 is not yet supported by pydantic-core).

1. Copy `.env.example` to `.env` / `apps/web/.env.local` and set login + data OAuth credentials.
2. Start Postgres, then API + worker + web (see below).

Seed data:

- Clients: **SMA Marketing** (`smamarketing.net`)
- Users: `admin@smamarketing.net` (SMA Admin), `team@smamarketing.net` (SMA Team → SMA Marketing)

### API

```bash
cd apps/api
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://localhost:5432/organiciq
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000 --host 127.0.0.1
# other terminal:
python -m app.worker
```

### Web

```bash
cd apps/web
npm install
npm run dev -- --hostname 127.0.0.1 --port 3000
```

## Phase 2 — GSC setup

1. Create a **separate** Google Cloud OAuth Web client for **data** access (not the Auth.js login client).
2. Authorized redirect URI: `http://127.0.0.1:8000/oauth/google/callback`
3. Set `GOOGLE_DATA_OAUTH_CLIENT_ID` / `GOOGLE_DATA_OAUTH_CLIENT_SECRET` on the API.
4. Enable Search Console API on the GCP project.
5. In Admin → Integrations (select a client):
   - **Connect Google** → consent → returns to Admin
   - **Load properties** → select GSC site → **Save property**
   - **Sync GSC 14 days** (enqueues `gsc_pages` + `gsc_queries`)
6. Watch Admin → Sync Jobs and Data Health.

### Manual acceptance gate (required before Phase 3)

Against **one client** and **14 days**, verify in GSC UI vs Organic IQ facts:

- [ ] Page totals align (same property / date window)
- [ ] Query records are real (no blank-query substitution)
- [ ] No overlapping / stuck jobs for the same source
- [ ] Watermarks / Data Health show fact-through dates
- [ ] Failures surface explicitly on Sync Jobs (never silent success)

GSC often lags 1–2 days; jobs may finish as `partial` with watermark at last available date — that is expected, not success-with-fake-data.

## Phase 3 — GA4 setup

Uses the **same Google Data OAuth** client as GSC. Enable **Google Analytics Data API** and **Google Analytics Admin API** on the GCP project.

1. In Admin → Integrations (select a client): **Reconnect Google** so consent includes Analytics (`analytics.readonly`) plus Search Console.
2. **Load properties** in the GA4 panel → select a property (`properties/{id}`) → **Save property**.
3. **Sync GA4 14 days** (enqueues source `ga4`: traffic + events).
4. Watch Admin → Sync Jobs and Data Health.

Direct / Unattributed is never auto-classified as Organic. Channel rules live in Admin → Configuration.

### Manual acceptance gate (required before Phase 4)

Against **one client** and **14 days**, verify in GA4 UI vs Organic IQ facts:

- [ ] Sessions / views on a landing page align (same property / date window)
- [ ] Google organic traffic is `organic_search`; Direct is `direct_unattributed`
- [ ] Key events (e.g. `generate_lead`) appear in `facts_ga4_events`
- [ ] Watermarks / Data Health show a GA4 fact-through date
- [ ] Failures surface explicitly on Sync Jobs (never silent success)

GA4 can lag a day; `partial` with watermark at last available date is expected.

## Phase 4 — SE Ranking Search setup

1. In SE Ranking → **API → Dashboard**, copy your API key.
2. Set `SE_RANKING_API_KEY` on the API (`apps/api/.env`).
3. Admin → Integrations (SMA Marketing):
   - **Load projects** → select the SE Ranking site → **Save project**
   - **Sync Search 14 days** (enqueues `se_ranking_search`)
4. Watch Admin → Sync Jobs / Data Health, then **Watch List → Search**.

Missing volume / visibility / SOV are stored as null — never invented.

### Manual acceptance gate (required before Phase 5)

Against **SMA Marketing** and **14 days**, verify in SE Ranking UI vs Organic IQ:

- [ ] Tracked keyword count / sample keywords align
- [ ] Positions and groups look correct for a few keywords
- [ ] Watch List Search shows real rows (no blank keywords)
- [ ] Data Health shows `se_ranking_search` fact-through
- [ ] Failures surface explicitly on Sync Jobs

## Phase 5 — SE Ranking AI setup

Uses the same mapped SE Ranking project as Search. **Clients → Integrations** (SMA Marketing):

1. **Sync AI 14 days** (enqueues `se_ranking_ai`)
2. Watch **Clients → Sync Jobs** / **Data Health**, then **Watch List → AI**

### What we ingest

All AI data comes from SE Ranking **AIRT** (AI Results Tracker) — the same tracked prompts you configure in SE Ranking, not the broader AI Search / Competitive Research universe.

| Layer | SE Ranking API | Organic IQ facts | Used for |
|-------|----------------|------------------|----------|
| **Tracked prompts** | `/project-management/airt/prompts` | `facts_ser_ai_prompts` | Watch List → AI (prompt text, group, engine) |
| **Per-prompt checks** | `/project-management/airt/prompt-rankings` | `facts_ser_ai_checks` | Watch List → AI (mentioned, cited, mention/link positions) |
| **Presence rollups** | `/project-management/airt/llm/statistics` (`top=0` and `top=3`) | `facts_ser_ai_tracker_stats` | Dashboard AI visibility |

**Dashboard AI metrics** (weighted across configured LLM engines by tracked prompt count):

- **Answers with your mention** — share of tracked prompts where your brand is mentioned
- **Answers with your link** — share of tracked prompts where your domain is cited with a link
- **Mention in Top 3** — share where your brand mention appears in the top 3 positions
- **Link in Top 3** — share where your domain link appears in the top 3 positions
- **Tracked prompt count** — total prompts in AIRT for the sync window

We do **not** ingest AI SOV, Competitive Research universe totals, or per-prompt visibility percentages when SE Ranking does not expose them via AIRT. Missing values are stored as null — never invented.

### Manual acceptance gate (required before Phase 6)

Against **SMA Marketing** and **14 days**, verify in SE Ranking **AI Results Tracker** vs Organic IQ:

- [ ] Tracked prompt count aligns with AIRT
- [ ] Watch List → AI: mentioned / cited flags match a few sample prompts
- [ ] Mention and citation positions look correct on sample rows
- [ ] Dashboard AI presence percentages align with SE Ranking Rankings report (same ~rounding; e.g. 2.5% → 3%)
- [ ] Data Health shows `se_ranking_ai` fact-through
- [ ] Failures surface explicitly on Sync Jobs

## Phase 6 — Dashboard

After GSC, GA4, and SE Ranking facts are synced, open **Dashboard** with SMA Marketing selected.

1. Set date range in the header (defaults to last 90 days).
2. Review **Conversions** (requires lead conversion definitions in **Clients → workspace → Conversions** — seed adds `generate_lead` for SMA).
3. Review **Visibility** — Search and AI are reported separately (no combined score):
   - **Search:** visibility, SOV, GSC impressions, average position (+ keyword distribution when synced)
   - **AI:** four AIRT presence metrics (mention, link, mention in top 3, link in top 3) + tracked prompt count
4. Review **Traffic** with period comparisons.
5. Confirm **Data Freshness** at the bottom matches **Clients → Data Health**.

Missing Search SOV remains null when SE Ranking does not return competitor visibility. AI metrics are null until AIRT sync completes — never invented.

### Manual acceptance gate (required before Phase 7)

Against **SMA Marketing** and your selected date range (try **14 days** and **90 days**):

- [ ] Dashboard loads Conversions → Visibility → Traffic (not a stub)
- [ ] Leads / lead rate match GA4 when conversion definitions exist
- [ ] GSC clicks/impressions and GA4 sessions/views align with source tools for the range
- [ ] SE Ranking Search metrics and AIRT presence stats appear when synced (nulls where sources provide none)
- [ ] AI dashboard row shows four presence metrics in one row (same layout as Search)
- [ ] Period comparison shows previous window values
- [ ] Data freshness table matches **Clients → Data Health** fact-through dates
- [ ] Changing client or date range updates dashboard metrics

## Phase 7 — 90-day validation

Expand **SMA Marketing** to a full **90-day** backfill, then prove ingestion stability and metric accuracy before onboarding more clients.

### Run the backfill

1. Open **Clients → SMA Marketing → Integrations**.
2. Click **Sync all sources 90 days** (or use the per-source **90 days** buttons on GSC, GA4, and SE Ranking).
3. Ensure the API worker is running (`python -m app.worker`).
4. Watch **Clients → Sync Jobs** until all jobs finish (`success` or expected `partial` with watermark).

Sources enqueued when mapped:

| Source | Job(s) |
|--------|--------|
| GSC | `gsc_pages`, `gsc_queries` |
| GA4 | `ga4` |
| SE Ranking | `se_ranking_search`, `se_ranking_ai` |

GSC and GA4 often lag 1–2 days; SE Ranking AI may finish `partial` when the API has no checks for the requested end date. Watermarks must reflect the last real fact date — never fake fill.

### Manual acceptance gate (required before Phase 8)

With dashboard date range set to **Last 90 days**:

- [ ] All mapped sources show fact-through dates in **Clients → Data Health**
- [ ] No stuck or overlapping jobs for the same source
- [ ] Dashboard Conversions / Visibility / Traffic load without errors for 90 days
- [ ] Period comparisons (current vs previous 90 days) behave correctly
- [ ] GSC, GA4, and SE Ranking spot-checks match source UIs for the same window
- [ ] AI AIRT presence metrics still align with SE Ranking Rankings report
- [ ] Re-running 90-day syncs is idempotent (no duplicate fact rows, stable watermarks)

Only after this passes should you onboard additional clients (Phase 8).

## Phase 8 — Multi-client (local)

Second test client for isolation and independent syncs:

| Client | Domain | Purpose |
|--------|--------|---------|
| SMA Marketing | `smamarketing.net` | Primary validation client (real integrations) |
| Beacon Industrial | `beaconindustrial.com` | Second client shell for mappings + isolation |

Re-run seed after pulling Phase 8 changes:

```bash
cd apps/api && source .venv/bin/activate && python -m app.seed
```

### Setup (Beacon Industrial)

1. Admin → **Clients** — confirm both clients appear.
2. Select **Beacon Industrial** → **Integrations**:
   - Connect Google (can reuse same Google account; map **different** GSC site + GA4 property if available).
   - Connect SE Ranking → map a **different** project than SMA.
3. **Sync 90 days** for Beacon only (Platform or client workspace).
4. Confirm SMA dashboard/metrics unchanged after Beacon syncs.

### Manual acceptance gate (required before Phase 9)

- [ ] Admin sees both clients; team user sees only assigned client(s)
- [ ] Integrations and property mappings are independent per client
- [ ] Sync jobs for client A do not block or mix with client B (same source allowed in parallel)
- [ ] Dashboard, jobs list, and data health are scoped by `X-OrganicIQ-Client-Id`
- [ ] Facts/watermarks for Beacon do not appear in SMA dashboard (and vice versa)
- [ ] Beacon 90-day sync completes (success or expected `partial` lag) without affecting SMA watermarks

Automated coverage: `pytest tests/test_phase8_multi_client.py tests/test_phase1.py`

## Phase 9 — Decision Engine (local)

Deterministic lever engine in `app/services/lever_engine.py` → `diagnose()`:

1. **Readiness gate** — requires Search Console page facts (`facts_gsc_pages`); crawl levers also need `facts_crawl_page_snapshots`
2. **Per-page cascade** — pages with ≥30 impressions, first matching lever wins (Technical → Internal Linking → SERP/CTR)
3. **Portfolio checks** — Structured Data/AI gap, Conversion Path (managed lead rate vs sessions)
4. **Scoring** — `0.4·impact + 0.3·confidence + 0.2·urgency + 0.1·(100−effort)`
5. **Rank** — top 14 recommendations returned to the UI

Content Expansion is scaffolded in the UI but has no trigger yet (needs topic-demand data).

### API

- `GET /decisions/diagnose?from=&to=` — live lever engine output (no persist)
- `POST /decisions/evaluate` — persist top recommendations for the period
- `PATCH /decisions/{id}` — update decision status
- `GET/PUT /decisions/thresholds` — per-client rule thresholds

Set `DECISION_ENGINE_ENABLED=false` to disable evaluation.

Run migration:

```bash
cd apps/api && alembic upgrade head
```

Automated coverage: `pytest tests/test_lever_engine_phase9.py tests/test_decisions_phase9.py`

## Phase map

| Phase | Focus | Status |
|-------|--------|--------|
| 1 | Foundation | Done |
| 2 | GSC ingestion | Done |
| 3 | GA4 ingestion | Done |
| 4 | SE Ranking Search | Done |
| 5 | SE Ranking AI (AIRT prompts, checks, presence stats) | Done |
| 6 | Dashboard | Done |
| 7 | 90-day validation (one client, ingestion stability + metric accuracy) | Done |
| 8 | Multi-client (isolation, mappings, stable syncs) | Done |
| 9 | **Decision Engine** — rules, thresholds, recommendations, Growth Action mapping | **Current** |
| 10 | Growth Actions & Annotations (Decision → task → Teamwork → measurement) | |
| 11 | Strategy & Content Plan | |
| 12 | Client portal | |

### When is the Decision Engine?

**Phase 9** — intentionally after the dashboard and data pipeline are proven trustworthy.

Prerequisites (from the build spec):

1. **Phase 6** — Dashboard acceptance (SMA Marketing, 14- and 90-day ranges)
2. **Phase 7** — 90-day validation (ingestion stability, accuracy, freshness, performance)
3. **Phase 8** — Multi-client rollout with strict isolation

Only then does Organic IQ start **decision rules**, configurable thresholds, stored decisions, Growth Action mapping, content planning signals, and evidence — all consuming the same normalized fact layer the Dashboard uses today. The nav item exists as a stub (`/decision-engine`) until Phase 9.

## Engineering rules (summary)

- Correctness over visual completeness
- No fake / placeholder metrics in production views
- One normalized fact layer for Dashboard and Decision Engine
- Client isolation in every backend query
- Durable, idempotent ingestion jobs with explicit freshness and failure
