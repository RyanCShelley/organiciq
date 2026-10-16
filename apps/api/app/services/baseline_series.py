"""A baseline from a monthly series: a clean recent window, ranges, and flags.

The flat 90-day (or 12-month) average this replaces treats a relaunch, a tracking
change, a spam spike and an ordinary month the same. Backtests on real client
data (13 clients for sessions, 5 for leads) found:

* Sessions, organic above all, are best set from the last few months. A longer
  average overshoots because the series keeps trending down: a flat 12-month
  average ran 15 to 20% high at a 12-month horizon.
* Lead rate has no single best window. A decayed average (half-life about three
  months) is the most robust, and a flat long window is never best.
* Lead rate is noisy (a typical miss of 25 to 35%) and estimates ran 10 to 25%
  optimistic, so goals are anchored on the low end of the range.
* Lead-definition drift (an event renamed, duplicated, or tracking that began
  late) costs more than any choice of window, so the series is checked for it
  and the window starts where the current site or tracking does.

Nothing here touches the database except `series_from_ga4`, so the method can be
tested, and run on a pasted CSV, without a client.
"""

from __future__ import annotations

import csv
import io
import math
import re
import statistics
from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.services import growth_calculator

#: Bumped whenever a number below changes, so a locked baseline says how it was made.
METHOD_VERSION = "baseline-2026-10-v1"

SESSIONS_WINDOW_MONTHS = 3
LEAD_RATE_WINDOW_MONTHS = 12
DEFAULT_HALF_LIFE_MONTHS = 3.0

#: Typical misses from the backtests, as a share of the estimate.
SESSIONS_RANGE_PCT = 20.0
LEAD_RANGE_PCT = 35.0
MAX_RANGE_PCT = 100.0

#: Under this many months in the current regime the baseline is provisional.
PROVISIONAL_UNDER_MONTHS = 3
THIN_UNDER_MONTHS = 6
#: Under this many leads in the rate window the range is widened.
LOW_LEAD_VOLUME = 30

SPIKE_SHARE = 0.40
SPIKE_MULTIPLE = 3.0
SHIFT_PCT = 25.0
#: A step in sessions this large, sustained, marks a change of site or tracking.
BREAK_PCT = 40.0
#: A month with at least this share of typical traffic and no leads is a tracking gap.
GAP_MIN_TRAFFIC_SHARE = 0.5
GAP_MIN_TYPICAL_LEADS = 3

BLOCKER, WARNING, INFO = "blocker", "warning", "info"


# --------------------------------------------------------------------------- #
# Months
# --------------------------------------------------------------------------- #

_MONTH_NAMES = {
    name: index
    for index, names in enumerate(
        (
            ("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"),
            ("may",), ("jun", "june"), ("jul", "july"), ("aug", "august"),
            ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
            ("dec", "december"),
        ),
        start=1,
    )
    for name in names
}


def normalize_month(value: str | date) -> str:
    """`2026-09`, `2026-09-14`, `202609`, `Sep 2026` and `9/2026` all become `2026-09`."""
    if isinstance(value, date):
        return f"{value.year:04d}-{value.month:02d}"
    text = str(value).strip()
    patterns = (
        (r"^(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?$", lambda m: (m[1], m[2])),
        (r"^(\d{4})(\d{2})$", lambda m: (m[1], m[2])),
        (r"^(\d{1,2})/(\d{1,2})/(\d{4})$", lambda m: (m[3], m[1])),
        (r"^(\d{1,2})/(\d{4})$", lambda m: (m[2], m[1])),
    )
    for pattern, pick in patterns:
        found = re.match(pattern, text)
        if found:
            year, month = (int(part) for part in pick(found))
            if 1 <= month <= 12 and 1900 <= year <= 2100:
                return f"{year:04d}-{month:02d}"
    named = re.match(r"^([A-Za-z]+)\.?,?\s+(\d{4})$", text)
    if named and named[1].lower() in _MONTH_NAMES:
        return f"{int(named[2]):04d}-{_MONTH_NAMES[named[1].lower()]:02d}"
    raise ValueError(f"“{value}” is not a month. Use a form like 2026-09 or Sep 2026.")


def _parts(key: str) -> tuple[int, int]:
    return int(key[:4]), int(key[5:7])


def month_end(key: str) -> date:
    year, month = _parts(key)
    return date(year, month, monthrange(year, month)[1])


def add_months(key: str, count: int) -> str:
    year, month = _parts(key)
    index = year * 12 + (month - 1) + count
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def months_between(first: str, last: str) -> list[str]:
    out, cursor = [], first
    while cursor <= last:
        out.append(cursor)
        cursor = add_months(cursor, 1)
    return out


# --------------------------------------------------------------------------- #
# Input
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MonthRow:
    month: str
    sessions: float
    leads: float
    organic_sessions: float | None = None
    #: Leads by event, where the source can say. Lets the flags see an event change.
    by_event: dict[str, float] = field(default_factory=dict)


_MONTH_COLUMNS = {"month", "date", "period", "year_month"}
_SESSION_COLUMNS = {"sessions", "visits", "total_sessions"}
_ORGANIC_COLUMNS = {"organic_sessions", "organic", "organic_search_sessions", "organic_search"}
_LEAD_COLUMNS = {"leads", "lead", "conversions", "key_events", "form_fills"}


def _canon(header: str) -> str:
    return re.sub(r"[\s\-]+", "_", header.strip().lower())


def _number(raw: str, label: str) -> float:
    text = (raw or "").strip().replace(",", "")
    if text in {"", "-", "—"}:
        raise ValueError(f"{label} is empty")
    try:
        value = float(text)
    except ValueError as exc:
        raise ValueError(f"{label} “{raw}” is not a number") from exc
    if value < 0 or math.isnan(value) or math.isinf(value):
        raise ValueError(f"{label} must be zero or more")
    return value


def parse_csv(text: str) -> tuple[list[MonthRow], list[str]]:
    """Monthly rows from pasted CSV, and a message for every row that was skipped.

    Columns: `month`, `sessions`, and either `leads` or one or more `lead_<event>`
    columns (which are summed and kept by event). `organic_sessions` is optional.
    """
    reader = csv.DictReader(io.StringIO((text or "").strip()))
    if not reader.fieldnames:
        raise ValueError("The CSV has no header row.")
    roles: dict[str, str] = {}
    event_columns: dict[str, str] = {}
    for header in reader.fieldnames:
        name = _canon(header)
        if name in _MONTH_COLUMNS:
            roles.setdefault("month", header)
        elif name in _SESSION_COLUMNS:
            roles.setdefault("sessions", header)
        elif name in _ORGANIC_COLUMNS:
            roles.setdefault("organic", header)
        elif name in _LEAD_COLUMNS:
            roles.setdefault("leads", header)
        elif name.startswith(("lead_", "event_")):
            event_columns[header] = header.split("_", 1)[1] if "_" in header else header
    missing = [need for need in ("month", "sessions") if need not in roles]
    if "leads" not in roles and not event_columns:
        missing.append("leads (or lead_<event> columns)")
    if missing:
        raise ValueError(f"The CSV needs a column for: {', '.join(missing)}.")

    rows: list[MonthRow] = []
    errors: list[str] = []
    seen: set[str] = set()
    for number, record in enumerate(reader, start=2):
        try:
            month = normalize_month(record[roles["month"]])
            if month in seen:
                raise ValueError(f"{month} appears more than once")
            sessions = _number(record[roles["sessions"]], "sessions")
            by_event = {
                label: _number(record[column], f"{label}") for column, label in event_columns.items()
            }
            leads = (
                _number(record[roles["leads"]], "leads") if "leads" in roles else sum(by_event.values())
            )
            organic = (
                _number(record[roles["organic"]], "organic sessions")
                if "organic" in roles and (record[roles["organic"]] or "").strip()
                else None
            )
        except ValueError as exc:
            errors.append(f"Row {number}: {exc}")
            continue
        seen.add(month)
        rows.append(MonthRow(month, sessions, leads, organic, by_event))
    if not rows:
        raise ValueError("No usable rows. " + (errors[0] if errors else ""))
    return sorted(rows, key=lambda row: row.month), errors


# --------------------------------------------------------------------------- #
# Method
# --------------------------------------------------------------------------- #


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _decayed_rate(rows: list[MonthRow], half_life: float) -> float:
    """Σ(w·leads) / Σ(w·sessions) in percent, newest month weighted most.

    Pooled over counts rather than averaging monthly rates, so a quiet month does
    not count as much as a busy one.
    """
    n = len(rows)
    weights = [0.5 ** ((n - 1 - index) / half_life) for index in range(n)]
    sessions = sum(w * row.sessions for w, row in zip(weights, rows))
    leads = sum(w * row.leads for w, row in zip(weights, rows))
    return leads / sessions * 100 if sessions > 0 else 0.0


def _detect_break(rows: list[MonthRow]) -> dict[str, Any] | None:
    """The latest month where sessions stepped away from the three before it and stayed.

    Two months must agree, except at the very end of the series where only one
    exists: there a drop counts and a rise does not, because a single month up is
    far more often a spike than a new site.
    """
    found = None
    for index in range(3, len(rows)):
        prior = _mean(row.sessions for row in rows[index - 3 : index])
        if prior <= 0:
            continue
        following = rows[index : index + 2]
        ratios = [row.sessions / prior for row in following]
        drop = all(ratio <= 1 - BREAK_PCT / 100 for ratio in ratios)
        rise = len(following) == 2 and all(ratio >= 1 / (1 - BREAK_PCT / 100) for ratio in ratios)
        if drop or rise:
            found = {
                "month": rows[index].month,
                "change_pct": round((_mean(ratios) - 1) * 100, 1),
            }
    return found


def _flag(code: str, level: str, message: str, months: list[str] | None, acknowledged: set[str]) -> dict:
    return {
        "code": code,
        "level": level,
        "message": message,
        "months": months or [],
        "acknowledged": code in acknowledged,
    }


def _round(value: float | None, places: int = 1) -> float | None:
    return None if value is None else round(value, places)


def analyze(
    rows: list[MonthRow],
    *,
    regime_start: str | date | None = None,
    as_of: date | None = None,
    half_life_months: float = DEFAULT_HALF_LIFE_MONTHS,
    plan: growth_calculator.PlanKey = "launch",
    acknowledged: Iterable[str] = (),
) -> dict[str, Any]:
    """The baseline, its ranges and its flags for one client.

    `regime_start` is the first month of the current site or tracking; months
    before it are shown but never averaged in. `as_of` is how far the data runs:
    the month it falls in is dropped as incomplete unless it is that month's last
    day. `acknowledged` names blocker flags somebody has accepted.
    """
    if not 0.5 <= half_life_months <= 24:
        raise ValueError("The half-life must be between half a month and 24 months.")
    ack = set(acknowledged)
    series = sorted(rows, key=lambda row: row.month)
    if len({row.month for row in series}) != len(series):
        raise ValueError("A month appears more than once in the series.")

    flags: list[dict] = []
    if as_of is not None and series and series[-1].month == normalize_month(as_of):
        if as_of < month_end(series[-1].month):
            flags.append(
                _flag(
                    "partial_month_dropped",
                    INFO,
                    f"{series[-1].month} is not over yet ({as_of.isoformat()}), so it is left out.",
                    [series[-1].month],
                    ack,
                )
            )
            series = series[:-1]
    if not series:
        raise ValueError("There is no complete month to build a baseline from.")

    expected = months_between(series[0].month, series[-1].month)
    absent = [month for month in expected if month not in {row.month for row in series}]

    start_key = normalize_month(regime_start) if regime_start else None
    if start_key and start_key > series[-1].month:
        raise ValueError("The baseline start is after the last month of data.")
    window = [row for row in series if start_key is None or row.month >= start_key]
    if not window:
        raise ValueError("No months fall on or after the baseline start.")
    n = len(window)
    window_months = {row.month for row in window}

    # -- where the current regime begins ------------------------------------
    detected = _detect_break(series)
    if detected and (start_key is None or start_key < detected["month"]):
        flags.append(
            _flag(
                "regime_break_unconfirmed",
                BLOCKER,
                f"Sessions stepped {detected['change_pct']:+.0f}% from {detected['month']} and stayed there. "
                f"If that was a relaunch, move the baseline start to {detected['month']}; "
                "otherwise acknowledge that the earlier months are comparable.",
                [detected["month"]],
                ack,
            )
        )

    # -- the numbers --------------------------------------------------------
    recent = window[-SESSIONS_WINDOW_MONTHS:]
    sessions_level = _mean(row.sessions for row in recent)
    organic_level = (
        _mean(row.organic_sessions for row in recent)
        if all(row.organic_sessions is not None for row in recent)
        else None
    )
    rate_rows = window[-LEAD_RATE_WINDOW_MONTHS:]
    lead_rate = _decayed_rate(rate_rows, half_life_months)
    leads_level = sessions_level * lead_rate / 100
    rate_lead_count = sum(row.leads for row in rate_rows)

    # Poisson noise on the count alone is ±1.96/√n, so few leads means a wide range.
    lead_pct = (
        min(MAX_RANGE_PCT, max(LEAD_RANGE_PCT, 196 / math.sqrt(rate_lead_count)))
        if rate_lead_count > 0
        else MAX_RANGE_PCT
    )

    def band(value: float, pct: float) -> dict[str, float]:
        return {"low": round(value * (1 - pct / 100), 2), "high": round(value * (1 + pct / 100), 2), "pct": round(pct, 1)}

    # Anchored on the low end: estimates ran 10 to 25% optimistic in the backtests.
    goal_leads = leads_level * (1 - lead_pct / 100)
    goal_rate = lead_rate * (1 - lead_pct / 100)
    projection_point = growth_calculator.project_leads(
        monthly_sessions=sessions_level, monthly_leads=leads_level, plan=plan
    )
    projection_goal = growth_calculator.project_leads(
        monthly_sessions=sessions_level, monthly_leads=goal_leads, plan=plan
    )

    # -- flags --------------------------------------------------------------
    total_leads = sum(row.leads for row in window)
    if total_leads == 0:
        flags.append(
            _flag("no_leads", BLOCKER, "No leads were recorded in the baseline window. Check the lead events.", None, ack)
        )

    median_sessions = statistics.median(row.sessions for row in window)
    median_leads = statistics.median(row.leads for row in window)
    leading_zero: list[str] = []
    for row in series:
        if row.leads > 0:
            break
        if row.sessions > 0:
            leading_zero.append(row.month)
    in_window_zero = [month for month in leading_zero if month in window_months]
    outside_zero = [month for month in leading_zero if month not in window_months]
    mid_gap = [
        row.month
        for row in window
        if row.leads == 0
        and row.month not in leading_zero
        and row.sessions >= GAP_MIN_TRAFFIC_SHARE * median_sessions
        and median_leads >= GAP_MIN_TYPICAL_LEADS
    ]
    if in_window_zero or mid_gap:
        gap = in_window_zero + mid_gap
        first_lead = next((row.month for row in series if row.leads > 0), None)
        advice = f" Move the baseline start to {first_lead}." if in_window_zero and first_lead else ""
        flags.append(
            _flag(
                "tracking_gap",
                BLOCKER,
                f"No leads in {', '.join(gap)} while traffic continued. Lead tracking probably was not working.{advice}",
                gap,
                ack,
            )
        )
    if outside_zero:
        flags.append(
            _flag(
                "tracking_start",
                INFO,
                f"Lead tracking appears to have started after {outside_zero[-1]}; those months are left out.",
                outside_zero,
                ack,
            )
        )

    events = sorted({name for row in series for name in row.by_event})
    if events:
        changes: list[str] = []
        first_window, last_window = window[0].month, window[-1].month
        for name in events:
            live = [row.month for row in series if row.by_event.get(name, 0) > 0]
            if not live:
                continue
            if live[-1] < add_months(last_window, -2) and live[-1] >= first_window:
                changes.append(f"“{name}” stopped after {live[-1]}")
            if live[0] > add_months(first_window, 2) and live[0] <= last_window:
                changes.append(f"“{name}” started in {live[0]}")
        if changes:
            flags.append(
                _flag(
                    "event_changed",
                    WARNING,
                    "The lead definition changed inside the window: " + "; ".join(changes)
                    + ". Counts before and after may not be comparable.",
                    None,
                    ack,
                )
            )

    if n >= THIN_UNDER_MONTHS and total_leads > 0:
        top = max(window, key=lambda row: row.leads)
        others = [row.leads for row in window if row is not top]
        others_median = statistics.median(others) if others else 0
        if top.leads / total_leads >= SPIKE_SHARE or (
            others_median >= GAP_MIN_TYPICAL_LEADS and top.leads >= SPIKE_MULTIPLE * others_median
        ):
            flags.append(
                _flag(
                    "lead_spike",
                    WARNING,
                    f"{top.month} has {top.leads:.0f} leads, far above the rest of the window. "
                    "Check for spam, a campaign, or a duplicated event.",
                    [top.month],
                    ack,
                )
            )
        spikes = []
        for row in window:
            rest = [other.sessions for other in window if other is not row]
            rest_median = statistics.median(rest) if rest else 0
            if rest_median > 0 and row.sessions >= SPIKE_MULTIPLE * rest_median:
                spikes.append(row.month)
        if spikes:
            flags.append(
                _flag(
                    "traffic_spike",
                    WARNING,
                    f"Sessions in {', '.join(spikes)} are more than {SPIKE_MULTIPLE:.0f}× the rest. Possibly bot traffic.",
                    spikes,
                    ack,
                )
            )
        earlier = window[:-3]
        if earlier:
            for label, values, floor in (
                ("sessions", [row.sessions for row in window], 0),
                ("leads", [row.leads for row in window], GAP_MIN_TYPICAL_LEADS),
            ):
                prior_median = statistics.median(values[:-3])
                recent_mean = _mean(values[-3:])
                if prior_median > floor and abs(recent_mean / prior_median - 1) * 100 >= SHIFT_PCT:
                    change = (recent_mean / prior_median - 1) * 100
                    flags.append(
                        _flag(
                            f"recent_shift_{label}",
                            WARNING,
                            f"The last 3 months of {label} are {change:+.0f}% against the months before them "
                            f"({recent_mean:,.0f} against a typical {prior_median:,.0f}).",
                            [row.month for row in window[-3:]],
                            ack,
                        )
                    )

    if n < PROVISIONAL_UNDER_MONTHS:
        flags.append(
            _flag(
                "provisional",
                INFO,
                f"Only {n} month{'' if n == 1 else 's'} in the current regime, so these numbers are provisional.",
                None,
                ack,
            )
        )
    elif n < THIN_UNDER_MONTHS:
        flags.append(
            _flag("short_regime", INFO, f"{n} months in the current regime. Treat the ranges as wide.", None, ack)
        )
    if rate_lead_count < LOW_LEAD_VOLUME:
        flags.append(
            _flag(
                "low_volume",
                WARNING,
                f"Only {rate_lead_count:.0f} lead{'' if rate_lead_count == 1 else 's'} in the lead-rate window, so the range is widened.",
                None,
                ack,
            )
        )
    gaps_in_window = [month for month in absent if month in window_months or (start_key is None)]
    if gaps_in_window:
        flags.append(
            _flag("missing_months", WARNING, f"No data for {', '.join(gaps_in_window)}.", gaps_in_window, ack)
        )

    order = {BLOCKER: 0, WARNING: 1, INFO: 2}
    flags.sort(key=lambda flag: order[flag["level"]])
    blockers = [flag for flag in flags if flag["level"] == BLOCKER]

    return {
        "method_version": METHOD_VERSION,
        "status": "provisional" if n < PROVISIONAL_UNDER_MONTHS else "draft",
        "parameters": {
            "half_life_months": half_life_months,
            "sessions_window_months": SESSIONS_WINDOW_MONTHS,
            "lead_rate_window_months": LEAD_RATE_WINDOW_MONTHS,
            "plan": plan,
        },
        "window": {
            "from": window[0].month,
            "to": window[-1].month,
            "months": n,
            "regime_start": start_key,
            "regime_start_source": "given" if start_key else "none",
            "suggested_regime_start": detected["month"] if detected else None,
        },
        "baseline": {
            "monthly_sessions": _round(sessions_level),
            "monthly_organic_sessions": _round(organic_level),
            "lead_rate_pct": _round(lead_rate, 3),
            "monthly_leads": _round(leads_level, 2),
        },
        "ranges": {
            "monthly_sessions": band(sessions_level, SESSIONS_RANGE_PCT),
            "monthly_organic_sessions": band(organic_level, SESSIONS_RANGE_PCT) if organic_level is not None else None,
            "lead_rate_pct": band(lead_rate, lead_pct),
            "monthly_leads": band(leads_level, lead_pct),
            "note": "Typical misses from backtests, not guarantees.",
        },
        "goal_basis": {
            "monthly_sessions": _round(sessions_level),
            "monthly_leads": round(goal_leads, 2),
            "lead_rate_pct": round(goal_rate, 3),
            "basis": "the low end of the lead range",
        },
        "references": {
            "mean_leads_last_3_months": _round(_mean(row.leads for row in window[-3:]), 2),
            "mean_leads_last_12_months": _round(_mean(row.leads for row in window[-12:]), 2),
            "pooled_lead_rate_pct_window": _round(
                sum(row.leads for row in window) / sum(row.sessions for row in window) * 100
                if sum(row.sessions for row in window) > 0
                else 0.0,
                3,
            ),
        },
        "projection": projection_goal,
        "projection_point": projection_point,
        "series": [
            {
                "month": row.month,
                "sessions": row.sessions,
                "organic_sessions": row.organic_sessions,
                "leads": row.leads,
                "lead_rate_pct": _round(row.leads / row.sessions * 100, 3) if row.sessions else None,
                "in_window": row.month in window_months,
                "by_event": row.by_event,
            }
            for row in series
        ],
        "flags": flags,
        "blockers": [flag["code"] for flag in blockers],
        "can_lock": all(flag["acknowledged"] for flag in blockers),
    }


# --------------------------------------------------------------------------- #
# GA4 source
# --------------------------------------------------------------------------- #


def series_from_ga4(
    db: Any, client: Any, *, months: int = 24, lead_events: list[str] | None = None
) -> tuple[list[MonthRow], dict[str, Any]]:
    """Monthly rows from the synced GA4 facts, and where they run to.

    The caller passes `info["as_of"]` to `analyze`, which drops an unfinished
    month. A first month the facts only partly cover is dropped here, so a short
    backfill is never averaged in as if it were a full month.
    """
    from sqlalchemy import case, func

    from app.models.config import OrganicChannel
    from app.models.ga4 import FactGa4Event, FactGa4Traffic
    from app.services.dashboard import _lead_event_names, _load_watermarks

    names = list(lead_events) if lead_events else _lead_event_names(db, client.id)
    if not names:
        raise ValueError("Declare at least one lead conversion event before building a baseline.")
    watermark = _load_watermarks(db, client.id).get("ga4")
    if watermark is None or watermark.fact_through_date is None:
        raise ValueError("No validated GA4 data yet. Sync GA4 first.")
    through = watermark.fact_through_date
    first_month = add_months(normalize_month(through), -(months - 1))
    start = date(int(first_month[:4]), int(first_month[5:7]), 1)

    earliest = (
        db.query(func.min(FactGa4Traffic.date)).filter(FactGa4Traffic.client_id == client.id).scalar()
    )
    if earliest is None:
        raise ValueError("There are no GA4 traffic facts for this client yet.")

    month_col = func.date_trunc("month", FactGa4Traffic.date)
    traffic = (
        db.query(
            month_col,
            func.coalesce(func.sum(FactGa4Traffic.sessions), 0),
            func.coalesce(
                func.sum(case((FactGa4Traffic.channel == OrganicChannel.ORGANIC_SEARCH, FactGa4Traffic.sessions), else_=0)),
                0,
            ),
        )
        .filter(FactGa4Traffic.client_id == client.id, FactGa4Traffic.date >= start, FactGa4Traffic.date <= through)
        .group_by(month_col)
        .all()
    )
    event_col = func.date_trunc("month", FactGa4Event.date)
    events = (
        db.query(event_col, FactGa4Event.event_name, func.coalesce(func.sum(FactGa4Event.event_count), 0))
        .filter(
            FactGa4Event.client_id == client.id,
            FactGa4Event.date >= start,
            FactGa4Event.date <= through,
            FactGa4Event.event_name.in_(names),
        )
        .group_by(event_col, FactGa4Event.event_name)
        .all()
    )
    by_month: dict[str, dict[str, float]] = {}
    for stamp, name, count in events:
        by_month.setdefault(normalize_month(stamp.date() if hasattr(stamp, "date") else stamp), {})[name] = float(count)

    rows = []
    for stamp, sessions, organic in sorted(traffic, key=lambda item: item[0]):
        key = normalize_month(stamp.date() if hasattr(stamp, "date") else stamp)
        per_event = by_month.get(key, {})
        rows.append(MonthRow(key, float(sessions), sum(per_event.values()), float(organic), per_event))

    notes: list[str] = []
    if rows and earliest.day > 1 and normalize_month(earliest) == rows[0].month:
        notes.append(f"{rows[0].month} is only partly covered by the synced data and was left out.")
        rows = rows[1:]
    return rows, {"as_of": through, "lead_events": names, "notes": notes}


def plan_for_client(db: Any, client: Any) -> growth_calculator.PlanKey:
    from app.models.client import Tier

    tier = db.query(Tier).filter(Tier.id == client.tier_id).one_or_none()
    return growth_calculator.plan_key_from_tier_name(tier.tier_name if tier else None)
