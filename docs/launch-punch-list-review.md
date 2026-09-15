# Launch punch list — code review

Source: `OrganicIQ App.md` (Obsidian → Development), app review 2026-09-14.
Reviewed against `5ce6aaf`.

Each item below is checked against what the code and data model actually
support, so the effort estimates mean something. Three items are cheaper than
they look because the data already exists; two are more serious than the note
describes.

---

## Read this first — where the note's diagnosis needs adjusting

**Decision Engine is not ignoring GA4 — but something worse is happening.**
The note reads the "Search Console / Crawl Audit" strip as evidence that GA4
isn't used. The engine does read GA4: `lever_engine.py` references
`FactGa4Event` / `FactGa4Traffic` in 14 places, and lead events drive the
Conversion Path lever. The strip is just a two-key readiness display
(`{"search_console", "crawl_audit"}`) that never mentions GA4.

The real problem is a hard gate:

```python
if gsc_rows == 0:
    return DiagnoseResult(ready=False,
        message="Search Console page facts are required before the Decision Engine can run.", ...)
```

A client with good GA4 conversion data but no Search Console gets **nothing** —
not even the Conversion Path lever, which needs no GSC at all. That is the fix
worth making; relabelling the strip is cosmetic next to it.

**Top pages from GA4 is a small job, not a big one.** `FactGa4Event` already
carries `normalized_url`, `event_name`, `event_count` and `date`, and
`FactGa4Traffic` carries `sessions` per URL. So per-page key events and the
session-to-key-event rate are *already ingested* — no new GA4 report, no
migration. It is a rewrite of one query plus the table columns.

What changes is the selection basis. `_top_pages` today picks the top 10 by GSC
clicks and joins GA4 on; it also returns `[]` outright when GSC has no rows. The
note wants pages ranked by contribution to conversions, which means leading with
GA4 and treating GSC as the optional join.

---

## Dashboard

| # | Item | Effort | Notes |
|---|------|--------|-------|
| D1 | ~~Baseline copy~~ **done** | XS | One string. Replaces the line added on 2026-09-10. |
| D2 | ~~Flip KPI order~~ **done** | XS | Baseline hero cards are currently sessions, leads, lead rate. Reorder three JSX blocks. |
| D3 | ~~Channels: add lead rate and % of monthly goal~~ **done** | S | Needs `sessions` per channel alongside leads. `FactGa4Traffic.channel` and `FactGa4Event.channel` both exist, so it is one wider query. % of goal = channel leads ÷ `period_lead_goal`. |
| D4 | ~~Top pages from GA4~~ **done** | M | See above. Columns: sessions, key events, views, session-to-key-event rate. Rank by key events. |

**D3 detail.** `leads_by_channel` currently returns `{channel, label, leads}`.
Adding `sessions` gives lead rate per channel for free; `period_lead_goal` is
already in the conversions payload, so goal contribution needs no new data.

**D4 caution.** Ranking by conversions means pages with zero key events fall off
the list entirely. Worth deciding whether the table should show top-by-conversion
only, or top-by-sessions with conversion columns so that high-traffic
non-converting pages stay visible — those are often the more actionable ones,
and the note's own framing ("a page's success is how it contributes to
conversions") arguably wants both.

---

## Watch List

| # | Item | Effort | Notes |
|---|------|--------|-------|
| W1 | ~~Date range does nothing → remove it~~ **done** | XS–M | Confirmed. See below. |
| W2 | Export / download | S | Reuse the CSV route added for the dashboard. |
| W3 | Cramped dates on the AI tab | XS | Column widths. |
| W4 | Position-distribution chart | S | **Data already exists.** |
| W5 | AI mention/link presence chart | S–M | Presence metrics exist; needs a time series. |
| W6 | Flag untracked keywords/prompts | L | New ingestion + new UI. |

**W1 — the note is right, and the reason matters.** The page resolves `from`/`to`
and then never passes them: `apiFetch("/watch-list/search", { clientId })`. The
endpoints accept no date parameters at all. They query `FactSerKeyword` and
`FactSerAiPrompt`, which are **current-state tables** — one row per keyword with
`current_position` and `checked_at`. A date range has no meaning against them.

So removing the picker from Watch List is correct for the page as designed
(two lines). Making dates *work* is a different feature: the time series lives in
`facts_ser_rankings` (already indexed on `client_id, date`), so a historical
view is buildable — but it is a new view, not a filter on this one. Decide which
you want before touching it.

**W4 — cheaper than expected.** `_keyword_distribution` already computes
`{top_3, top_10, top_20, beyond_20, not_ranking}` and ships it in the dashboard
payload under `visibility.search.keyword_distribution`. The chart needs the
number surfaced on Watch List, not new data.

**W6.** SE Ranking has no insights API, as the note says. The AI-search endpoint
could surface related prompts/keywords, but this is a new fetch, new staging and
facts, new UI, and ongoing quota. Genuinely post-launch.

---

## Content Opp

| # | Item | Effort | Notes |
|---|------|--------|-------|
| C1 | Colour-code page type and opportunity type | S | The design defines the chips (`tagBg`/`tagFg` per type: CTR gap, Striking, Topic gap, Near win); the implementation renders no type chip. Straight port. |
| C2 | Cross-reference SE Ranking | M–L | Needs a join key between GSC queries and SE Ranking keywords — exact-match text is the obvious one and will be lossy. Worth scoping separately. |

---

## Decision Engine

| # | Item | Effort | Notes |
|---|------|--------|-------|
| E1 | ~~GSC hard-gate blocks GA4-only levers~~ **done** | M | **Highest-value item on this list.** See top of doc. |
| E2 | ~~Readiness strip confusing / omits GA4~~ **done** | S | Add `ga4` to the readiness dict and label the keys in plain language. Do this with E1 so the strip reflects real behaviour. |

---

## Client settings — the biggest job, as the note says

| # | Item | Effort | Notes |
|---|------|--------|-------|
| S1 | ~~Sheet URL renders as a link~~ **done** | XS | Currently a bare input. |
| S2 | "Build snapshot from GA4", not "preview" | S | Naming + making apply the primary action. |
| S3 | Baseline date is settable; window anchors to it | M | Today `to_date` is hardcoded to the GA4 watermark and `from_date = to − 29d`. No way to anchor to Aug 1. |
| S4 | 90-day lookback averaged to monthly | S | Once S3 makes the window a parameter, this is a default change plus the existing `_scale_to_monthly`. |
| S5 | Persist 3/6/9/12-month projections | M | **Checkpoints already exist** — `growth_calculator.project_leads` returns Today / 3 / 6 / 9 / 12 with labels. They are returned in the preview and then thrown away. Needs a JSONB column on `clients` + migration. |
| S6 | Show benchmarks on dashboard + account record | S | Depends on S5. |

**S3 is the structural one.** `preview_baseline_from_ga4` derives its window
entirely from the GA4 watermark:

```python
to_date   = ga4_wm.fact_through_date          # ≈ today
from_date = to_date - timedelta(days=29)      # fixed 30-day window
```

Making the anchor a parameter touches the service, both endpoints, the schema
and the panel. Everything downstream (S4, S5, S6) sits on top of it, so sequence
it first.

One constraint to design around: an anchored window can land where GA4 facts do
not exist. Backfill only goes as far as the client's synced history, and
`_effective_range` already clips to the watermark. Setting a baseline of Aug 1
with a 90-day lookback needs facts back to early May — so the panel has to say
plainly when the requested window is only partly covered, rather than silently
averaging over a shorter span and reporting it as 90 days.

---

## Suggested order

1. **E1 + E2** — Decision Engine gate and readiness. Highest value; a client
   without GSC currently gets an empty engine.
2. **D1, D2, W1, W3, S1, C1** — a half-day of copy, ordering and cleanup.
3. **D3, D4** — the leads-focused dashboard the note is really asking for. No
   new ingestion.
4. **S3 → S4 → S5 → S6** — baseline rework, in that order.
5. **W2, W4** — export and distribution chart; both reuse what exists.
6. **W5, C2, W6** — post-launch.

## Decisions (2026-09-14)

**D4 — top pages.** Not ranked by conversions alone. Pages with conversion
impact rank higher, but pages that could move traffic and visibility stay
visible. So: a blended rank that weights key events above sessions rather than
filtering to converters, with GA4 columns added alongside the GSC ones the page
shows today.

**W1 — Watch List dates.** Remove the picker. The ranking distribution chart
carries the over-time story instead, so no historical view is needed on this
page.

**S5 — projections.** Freeze the checkpoints at the point the baseline is
built. Re-running is **manual and on demand** — a "Set / re-run projections"
control in Client settings — with an annual cadence as the expectation rather
than an automatic job. Stored projections therefore carry a `generated_on`
date so a stale set reads as stale and prompts the re-run.
