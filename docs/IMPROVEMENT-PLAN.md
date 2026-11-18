# Organic IQ — Improvement Plan & Master Checklist

Last updated: 2026-11-18

---

## Phase 1: Quick Fixes & UX Polish

### Client Picker & Navigation
- [x] **Client Picker search & active-account scroll** (`apps/web-v2/components/layout/ClientPicker.tsx`):
  - Always display a high-contrast, sticky search input at the top of the dropdown (remove the `clients.length > 8` gate).
  - Auto-focus the search input when the dropdown opens.
  - Scroll the currently active client into view (`scrollIntoView({ block: "nearest" })`) when opening the dropdown.

### Baseline & Goal Math
- [x] **Baseline goal floor** (`apps/api/app/services/growth_calculator.py`, `apps/api/app/services/baseline_series.py`, `apps/api/app/services/lead_goals.py`):
  - Goal starts from the typical figure and never sits below the baseline (e.g., `21 → 19`), including home screen next-checkpoint goals.
  - *Note:* Revisit and re-run the `TRAFFIC_DECLINE_12MO = 12.8` assumption (originally derived from GA4 MCP + Claude analysis; verify AI Overviews impact).
- [ ] **3-Pillar Baseline Snapshot** (Visibility + Traffic + Leads):
  - Expand `BaselineVersion.snapshot` to capture starting Visibility (GSC/Bing/Watchlist/SoV/LLM/Site Health), Traffic (GA4 channels + top pages), and Leads, with 30-day avg + 90-day total and CSV export.

### LLM Visibility UX & Schedule
- [x] **Rename `"Full run"` → `"Prompt Details"`** (`apps/web-v2/components/LlmScreen.tsx`).
- [x] **Group Prompt Details by prompt (remove 4-row confusion)**:
  - Show one row per prompt indicating whether/where the brand is ranking/cited across platforms.
  - Expand a prompt row to inspect per-LLM details (ChatGPT, Perplexity, Gemini, Claude).
- [x] **Prompt search**: Add a quick search/filter box to filter prompts across Prompt Details and Query Summary.
- [x] **Query summary**: Show ranking/presence clearly per area/platform (`#rank` formatting).
- [x] **Overview tab**: Add a Share of Voice summary card/section on the Overview tab (it is an overview metric).
- [ ] **Verify weekly schedule**: Confirm `enqueue_due_llm_runs` (`LLM_RUN_INTERVAL_DAYS = 7` in `apps/api/app/services/daily_sync.py`) is firing reliably for worked clients in production.

### Onboarding & Job Cleanup
- [x] **Remove SE Ranking AI search leftovers** from onboarding/connections (`apps/web-v2/app/(app)/[clientSlug]/settings/connections/actions.ts`).

---

## Phase 2: Site Health & Search Visibility Overhaul

### Site Health (`apps/api/app/services/site_health.py`, `apps/web-v2/components/SiteHealth.tsx`)
- [ ] **Explicit duplicate/missing breakdowns**:
  - Separate "Missing meta description/title" from "Duplicate meta description/title".
  - Group duplicates by the shared title/description value so the team can see which exact pages share the same text.
- [ ] **Group all issues by URL (SEO Health + GEO Readiness)**:
  - Merge multiple findings for the same page (e.g., homepage missing Organization markup + missing structured data) into a single per-URL entry.
  - Provide a **By Page** view with explicit prescribed fixes so the team can work page-by-page.

### Search Visibility (`apps/api/app/services/search_visibility.py`, `apps/web-v2/components/SearchVisibility.tsx`)
- [ ] **GSC "Unsung Heroes" (untracked opportunities)**:
  - Surface relevant, high-impression / rising Search Console queries not currently on the client's watchlist, with a quick "Add to watchlist" action.
- [ ] **More Bing visibility data**:
  - Elevate Bing impressions, clicks, and position trends alongside GSC in the main visibility view and movers.
- [ ] **Monthly visibility check annotations**:
  - Add a quick "Log visibility check" action (wired to `v2_annotations`) to record monthly check notes and render markers on the visibility trend chart.

---

## Phase 3: Decision Engine Remaining

- [x] Engine opens on the page the person selected instead of "best page" (planner still needs alignment if applicable).
- [x] Monthly automatic selection: apply "fewer strong actions, no quota filling" rule to the run that fills plan slots.
- [ ] **Reviewer feedback (8 rejection reasons)**: Add DB column + Alembic migration and surface/capture the 8 rejection reasons in the review UI.
- [ ] **Page-type checklists**: Add dedicated checklists for `service`, `location`, `category`, and `homepage` pages.
- [ ] **Diagnose screens**: Apply intent, page type, and fit to the plain Diagnose screens (not only growth actions).
- [ ] **Client focus ordering**: Drive action ordering by client focus (e.g., `Leads` puts calls to action first).
- [ ] **FAQ enhancements**:
  - Pull People Also Ask (PAA) questions.
  - Check for an existing FAQ page and suggest linking to it.
- [ ] **New action**: `"Rewrite the meta for clicks"`.
- [ ] **Custom steps**: Allow adding custom steps to an action.
- [ ] **Page history & client style notes**: Store and display page edit/action history and client tone/style notes.
- [ ] **DataForSEO wider SERPs**: Pull broader SERP data for searches that aren't currently tracked.

---

## Phase 4: Guided Setup, Content Tools & All-Clients Overview

### Setup (Amanda's notes)
- [ ] **Guided setup**: Step-by-step onboarding using the existing unused checklist.
- [ ] **Clearer baseline screen**: Simplify and clarify baseline configuration and projections.
- [ ] **In-app watchlist editor**: Add and edit the watchlist in the app with Search Console keyword suggestions.

### Content Tools
- [ ] **Content gaps**: Filter out irrelevant results.
- [ ] **Content optimizer**: Add ad-hoc keyword input for one-off page optimizations.
- [ ] **Content sources**: Keep sitemap ingestion; remove unused feeds.

### All-Clients Overview
- [ ] **Home screen (`apps/web-v2/app/(app)/page.tsx`)**: Replace auto-redirect to `clients[0]` with a **sortable table** showing every client's visibility, traffic, and leads.

---

## Open Research / Follow-ups
- [ ] Re-run research on the **12.8% yearly traffic decline** (verify AI Overviews impact across client cohort).
- [ ] Confirm where the **"max of 3, in priority order"** limit lives.
- [ ] Confirm who added the **groups in SE Ranking** (app currently only reads them).
- [ ] Resolve the two **internal-link decisions** from the earlier review.
