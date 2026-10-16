# Baseline calculator

Phase 1 of the baseline rebuild: the engine, a CSV input and two read-only API routes.
Nothing here writes to the database. Locking, versions and the screen are phases 2 and 3.

Code: `apps/api/app/services/baseline_series.py`. Tests: `apps/api/tests/test_baseline_series.py`.

## Why it exists

The old preview divided one flat window (90 days by default) into a monthly number. A
relaunch, a tracking change, a spam spike and a normal month all counted the same, and
the goal was built on top of whatever came out.

## The method

Everything starts at the **baseline start**: the first month of the current site or
tracking. Earlier months stay on the chart and are never averaged in.

| Number | How |
|---|---|
| Sessions (and Organic Search) | mean of the last 3 months of the window |
| Lead rate | decayed pooled rate over up to 12 months, half-life 3 months: Σ(w·leads) / Σ(w·sessions) |
| Leads per month | sessions × lead rate, so the three always agree |
| Range, sessions | ±20% |
| Range, leads and lead rate | ±35%, widened to ±196/√n % when the window has few leads |
| Goal basis | the **low end** of the lead range |
| Projection | `growth_calculator.project_leads`, unchanged (12.8% traffic decline kept), built from the goal basis; `projection_point` is the same from the estimate |

Under 3 months in the window the status is `provisional`.

### Evidence (backtests, October 2026)

* Sessions, 13 clients, ~200 to 320 overlapping forecasts per horizon. For organic, a flat
  12-month average missed by 27% and ran ~20% high at 12 months; last-3-months missed by
  23% (+12% bias); the calculator's fixed decline was the least biased (+4%). Fitted
  trend and seasonal models were no better than that (tuning the damping did not hold up
  out of sample). Typical miss for any method: 15 to 20%.
* Lead rate, 5 clients with a usable series. No single window wins; a decayed average
  (half-life 3) was the most robust at 12 months (32% against 40% for last-3 and 46% for
  last-12). Shrinking toward other clients' absolute rates was worse (rates differ too
  much). Typical miss 25 to 35%, with estimates 10 to 25% optimistic: hence the low end.
* Lead-definition drift (events renamed, duplicated, tracking started late, phone calls
  added midway) was a larger error than any window choice: hence the flags below.

These are indicative: few clients, overlapping windows, sessions tested far more than
leads. Re-run them as more clients get clean series.

## Flags

`blocker` flags stop a lock until acknowledged (phase 2 enforces it; `can_lock` already
reports it): `no_leads`, `tracking_gap`, `regime_break_unconfirmed`.

`warning`: `event_changed`, `lead_spike`, `traffic_spike`, `recent_shift_sessions`,
`recent_shift_leads`, `low_volume`, `missing_months`. `info`: `provisional`,
`short_regime`, `tracking_start`, `partial_month_dropped`.

A break is a step of 40% or more in sessions against the previous three months that holds
for two months (or, at the very end of the data, one month down; a single month up reads
as a spike, not a new site).

## API (both read-only, staff)

* `GET /clients/{id}/baseline/series` from synced GA4. Query: `months` (6 to 48, default
  24), `regime_start`, `half_life_months`, `lead_event` (repeatable; defaults to the
  client's lead conversion definitions), `acknowledge` (repeatable flag codes).
* `POST /clients/{id}/baseline/series` with `{csv_text, regime_start?, as_of?,
  half_life_months?, acknowledged?}`.

CSV columns: `month`, `sessions`, and `leads` or `lead_<event>` columns; `organic_sessions`
optional. Months may be `2026-09`, `Sep 2026`, `9/2026`, `202609`.

## Not yet

Lock and versions (any staff may lock; a lock needs every blocker acknowledged), the
settings screen, the 24-month GA4 backfill, the monthly actual-versus-projected log, test-lead
exclusion (waiting on the ACC Tech work), and a separate traffic-decline setting for total
sessions (the test found 12.8% too steep for it).
