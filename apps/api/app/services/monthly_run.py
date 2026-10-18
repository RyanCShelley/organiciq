"""Run the engine for a month and save the record.

The page reads the saved record and never recomputes. That is the whole point
of saving it: a run is a thing that happened on a date, with the data it had,
and a reader comparing this month to last is comparing two decisions rather
than two recalculations.

The record is built to `monthly-record.schema.json`, which the client page
renders field for field.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.decisions.triage import (
    WITHHELD,
    Branch,
    Status,
    Triage,
    assess_leads,
    assess_traffic,
    assess_visibility,
    select_constraint,
    summarise_branch,
)
from app.models.annotation import Annotation
from app.models.client import WORKED_STATUSES, Client
from app.decisions.catalog import (
    BLOCKED_ACTIONS,
    LEAD_ACTIONS,
    TRAFFIC_ACTIONS,
    VISIBILITY_ACTIONS,
    prescribe,
    prescribe_page,
)
from app.decisions.page_targets import rank_for_leads, rank_for_traffic
from app.decisions.content_gaps import (
    content_words,
    prescribe_demand,
    prescribe_term,
    rank_demand,
    rank_for_content,
)
from app.decisions.update_catalog import UPDATE_ACTIONS, rank_for_updates
from app.services.content_gap_signals import scan_term_gaps
from app.services.demand_gaps import LOOKBACK_DAYS, scan_demand_gaps
from app.decisions.incidents import check as check_incidents
from app.decisions.overrides import Exclusion, is_excluded
from app.decisions.slots import Considered, Prescription, fill_pool, fill_slots
from app.decisions.targets import rank_candidates
from app.models.decision import ConstraintOverride, ExcludedPage, MonthlyRecord
from app.models.gsc import FactGscPage
from app.models.ga4 import FactGa4Traffic
from app.services.plan_allowances import resolve_plan_allowances
from app.services.incident_signals import read_incident_signals
from app.services.page_signals import load_page_candidates
from app.services.results import capture_before, previous_results
from app.services.target_signals import load_target_inputs
from app.services.triage_signals import lead_signals, traffic_signals, visibility_signals
from app.services.decision_measurements import measure as measure_outcomes

logger = logging.getLogger("organiciq.monthly_run")

#: A source older than this and the run is withheld rather than served. Acting
#: on numbers that stopped updating is worse than acting on none.
STALE_DAYS = 7

#: When an action is judged. The spec checks at 28 to 45 days; 28 is the
#: earliest a position change means anything.
CHECK_AFTER_DAYS = 28

#: A relaunch, migration or domain change inside this window forces Visibility.
RELAUNCH_WINDOW_DAYS = 180

#: Words in an annotation that mean the site changed underneath its rankings.
RELAUNCH_WORDS = ("relaunch", "migration", "migrated", "redesign", "domain change")


def _slot_row(client, month: str, slot, today: date) -> dict:
    """One filled slot, as the record stores it.

    Written once because the growth plan and the retainer pools must look
    identical to everything downstream: `slots_in_record` reads them with
    one loop, and the page renders them with one card.
    """
    return {
        "action_uid": action_uid(client.slug, month, slot.prescription),
        "slot": slot.slot,
        "id": slot.prescription.action_id,
        "title": slot.prescription.title,
        "branch": slot.prescription.branch.value,
        "spillover": slot.spillover,
        "target_url": slot.prescription.target_url,
        "term": slot.prescription.term,
        "score": round(slot.prescription.score, 1),
        "effort_min": slot.prescription.effort_min,
        "why": slot.prescription.why,
        "evidence": list(slot.prescription.evidence),
        "done_when": slot.prescription.done_when,
        "steps": list(slot.prescription.steps),
        "metric": slot.prescription.metric,
        # What the results loop reads to judge it. Stored on the record so a
        # check months later uses the key the action was prescribed with,
        # not whatever the catalog says by then.
        "metric_key": slot.prescription.metric_key,
        "check_on": (
            today
            + timedelta(days=slot.prescription.check_after_days or CHECK_AFTER_DAYS)
        ).isoformat(),
        "flags": list(slot.prescription.flags),
    }


def _candidate_row(client, month: str, considered, today: date) -> dict:
    """One thing the engine weighed, slotted or not.

    Carries `check_on` like a slotted action does: a candidate can be put
    into the plan by hand, and from that moment the results loop has to
    know when to judge it.
    """
    return {
        "action_uid": action_uid(client.slug, month, considered.prescription),
        "slot": considered.slot,
        "spillover": considered.spillover,
        "not_slotted_because": considered.reason,
        "id": considered.prescription.action_id,
        "title": considered.prescription.title,
        "branch": considered.prescription.branch.value,
        "target_url": considered.prescription.target_url,
        "term": considered.prescription.term,
        "score": round(considered.prescription.score, 1),
        "effort_min": considered.prescription.effort_min,
        "why": considered.prescription.why,
        "evidence": list(considered.prescription.evidence),
        "done_when": considered.prescription.done_when,
        "steps": list(considered.prescription.steps),
        "metric": considered.prescription.metric,
        "metric_key": considered.prescription.metric_key,
        "check_on": (
            today
            + timedelta(
                days=considered.prescription.check_after_days or CHECK_AFTER_DAYS
            )
        ).isoformat(),
        "flags": list(considered.prescription.flags),
    }


def action_uid(slug: str, month: str, prescription) -> str:
    """A stable name for one action on one page.

    Keyed on what the action *is*, not on the slot it happened to take. The
    slot number was the key until now, so a re-run that reshuffled the order
    carried an assignment onto a different action — and an action outside
    the slots had no name at all, which is why none of them could be
    assigned, sent or measured.
    """
    import hashlib

    seed = f"{prescription.action_id}|{prescription.target_url or ''}|{prescription.term or ''}"
    digest = hashlib.sha1(seed.encode()).hexdigest()[:8]
    return f"{slug}-{month}-{prescription.action_id.lower()}-{digest}"


def month_key(when: date) -> str:
    return f"{when.year:04d}-{when.month:02d}"


def as_of(month: str, *, today: date | None = None) -> date:
    """The day a run for `month` is made as of.

    The last day of that month, or today, whichever comes first. Running
    October in November judges the whole of October; running October on the
    14th judges October to the 14th. One rule covers "I run last month's data
    at the start of this one" and "show me where we are so far".

    Raises ValueError on anything that is not `YYYY-MM`, because a bad month
    silently falling back to today is how a run gets filed under the wrong
    one.
    """
    try:
        year, month_number = (int(part) for part in month.split("-"))
        last_day = calendar.monthrange(year, month_number)[1]
        month_end = date(year, month_number, last_day)
    except (ValueError, calendar.IllegalMonthError) as exc:
        raise ValueError(f"{month!r} is not a month in YYYY-MM form.") from exc
    return min(month_end, today or date.today())


def _previous_month(key: str) -> str:
    year, month = (int(part) for part in key.split("-"))
    return f"{year - 1:04d}-12" if month == 1 else f"{year:04d}-{month - 1:02d}"


def _last_fact(db: Session, model, column, client_id: UUID) -> date | None:
    return (
        db.query(func.max(column)).filter(model.client_id == client_id).scalar()
    )


def _stale_reason(db: Session, client: Client, today: date) -> str | None:
    """Which source stopped reporting, if any.

    Read from the facts rather than the watermarks. A watermark is a claim
    about what was fetched, and a watermark that advanced past data that was
    never there is what hid a broken Search Console sync for fifteen days.
    """
    for label, model, column in (
        ("Search Console", FactGscPage, FactGscPage.date),
        ("GA4", FactGa4Traffic, FactGa4Traffic.date),
    ):
        newest = _last_fact(db, model, column, client.id)
        if newest is None:
            return f"No {label} data at all for this client."
        age = (today - newest).days
        if age > STALE_DAYS:
            return (
                f"{label} data is {age} days stale — newest day on record is "
                f"{newest.isoformat()}. Nothing is served off numbers that "
                "stopped updating."
            )
    return None


def _relaunched_recently(db: Session, client: Client, today: date) -> bool:
    since = today - timedelta(days=RELAUNCH_WINDOW_DAYS)
    rows = (
        db.query(Annotation)
        .filter(Annotation.client_id == client.id, Annotation.date >= since, Annotation.date <= today)
        .all()
    )
    for row in rows:
        text = (row.description or "").lower()
        if any(word in text for word in RELAUNCH_WORDS):
            return True
    return False


def _confidence(triage: Triage, *, blocked_inputs: list[str]) -> tuple[str, list[dict]]:
    """High, medium or low, and what to check before assigning.

    A blocked test is a missing input, and a run with missing inputs is not a
    run anyone should act on without being told which.
    """
    reasons = [
        {"code": "missing_input", "text": text} for text in sorted(set(blocked_inputs))
    ]
    if triage.constraint == WITHHELD:
        return "low", reasons
    if len(reasons) >= 3:
        return "low", reasons
    if reasons:
        return "medium", reasons
    return "high", reasons


def _held_since(db: Session, client: Client, month: str, constraint: str) -> str:
    """The month this constraint was first named.

    Without it the two-month hold cannot exist, and the page cannot say "month
    two" — which is the difference between a client being worked on and a
    client being rediscovered every month.
    """
    previous = (
        db.query(MonthlyRecord)
        .filter(
            MonthlyRecord.client_id == client.id,
            MonthlyRecord.month == _previous_month(month),
        )
        .one_or_none()
    )
    if previous is not None and previous.constraint_name == constraint:
        return previous.held_since
    return month


def load_exclusions(
    db: Session, client: Client, *, today: date | None = None
) -> list[Exclusion]:
    """Pages this run must not prescribe for.

    Two sources. `excluded_pages` is a standing decision — "we are not
    working on careers" — and `refresh_queue` is this month only: a page
    already booked for a rewrite is paid for out of the content allowance,
    so spending a growth slot on it charges the client twice for one job.
    The old lever engine honoured the second and the new one did not.
    """
    from app.models.config import RefreshQueueEntry

    today = today or date.today()
    out = [
        Exclusion(url_pattern=row.url_pattern, reason=row.reason)
        for row in db.query(ExcludedPage).filter(ExcludedPage.client_id == client.id)
    ]
    out.extend(
        Exclusion(
            url_pattern=row.normalized_url,
            reason="already booked for a content rewrite this month",
        )
        for row in db.query(RefreshQueueEntry).filter(
            RefreshQueueEntry.client_id == client.id,
            RefreshQueueEntry.month == today.replace(day=1),
        )
        if row.normalized_url
    )
    return out


def load_override(db: Session, client: Client, month: str) -> ConstraintOverride | None:
    return (
        db.query(ConstraintOverride)
        .filter(
            ConstraintOverride.client_id == client.id,
            ConstraintOverride.month == month,
        )
        .one_or_none()
    )


def build_record(
    db: Session, client: Client, *, today: date | None = None
) -> dict:
    """Run Decision 1 and return the record, without saving it."""
    today = today or date.today()
    month = month_key(today)
    # No per-client overrides. The rules read each threshold with an inline
    # default, and the override store that used to feed this was empty in
    # production and tuned only the engine that has been removed — it offered
    # dials that turned nothing, which is what the guard test existed to stop.
    thresholds: dict = {}

    # Clamped to the run's own day. Running October in November would
    # otherwise take GSC's window up to November's newest row and report
    # "data through Nov 5" on a record filed as October.
    gsc_newest = _last_fact(db, FactGscPage, FactGscPage.date, client.id)
    if gsc_newest and gsc_newest > today:
        gsc_newest = today
    gsc_period = (today - timedelta(days=29), gsc_newest) if gsc_newest else None
    ai_period = (today - timedelta(days=29), today)

    branches = [
        summarise_branch(
            Branch.VISIBILITY,
            assess_visibility(
                visibility_signals(db, client, today=today, ai_period=ai_period),
                thresholds=thresholds,
            ),
        ),
        summarise_branch(
            Branch.TRAFFIC,
            assess_traffic(
                traffic_signals(db, client, today=today, gsc_period=gsc_period),
                thresholds=thresholds,
            ),
        ),
        summarise_branch(
            Branch.LEADS,
            assess_leads(lead_signals(db, client, today=today), thresholds=thresholds),
        ),
    ]

    triage = select_constraint(
        branches,
        relaunch_within_180d=_relaunched_recently(db, client, today),
        withheld_reason=_stale_reason(db, client, today),
    )

    # Somebody overruled it. The branches keep the statuses the tests
    # produced — the override changes which one gets the slots, not what the
    # numbers said, because a record that rewrote the evidence to match the
    # decision would be unreadable a month later.
    override = load_override(db, client, month)
    engine_said = triage.constraint
    if override is not None and triage.constraint != WITHHELD:
        triage = Triage(
            constraint=override.constraint_name,
            reason_text=override.reason,
            branches=triage.branches,
            override="manual",
        )

    blocked_inputs = [
        test.missing
        for branch in branches
        for test in branch.tests
        if test.status is Status.BLOCKED and test.missing
    ]
    confidence, confidence_reasons = _confidence(triage, blocked_inputs=blocked_inputs)

    exclusions = load_exclusions(db, client, today=today)
    allowances = resolve_plan_allowances(client, getattr(client, "tier", None))
    slots = 0 if triage.constraint == WITHHELD else allowances.growth_action_allowance

    # ── Decisions 2 and 3 ───────────────────────────────────────────────
    inputs = load_target_inputs(db, client, exclusions=exclusions)
    ranked = rank_candidates(inputs.candidates, thresholds=thresholds)
    prescriptions = []
    findings = []
    # Missing volume limits ranking confidence; it must not erase a strategic target.
    from app.decisions.targets import score_candidate
    ranked_terms = {s.candidate.keyword for s in ranked}
    review_targets = ranked + [score_candidate(c) for c in inputs.candidates if c.keyword not in ranked_terms]
    for scored in review_targets:
        page = inputs.pages.get(scored.candidate.target_url)
        if page is not None and page.page_type != "utility":
            findings.extend(found for rule in VISIBILITY_ACTIONS if (found := rule(scored, page)) is not None)
    for scored in ranked:
        url = scored.candidate.target_url
        page = inputs.pages.get(url) if url else None
        if page is None or page.page_type == "utility":
            # Nothing crawled for this page, so no trigger can be tested
            # against it. V-6 is the exception and needs no page facts.
            continue
        found = prescribe(scored, page)
        if found is not None:
            prescriptions.append(found)

    # Traffic and Leads ask about the page, not the term, so they come from
    # their own candidates. Until these existed, a client constrained on
    # Traffic got a plan of Visibility spillover or an empty one — the engine
    # named the problem and then prescribed for a different branch.
    from app.services.page_eligibility import classify_page_url
    page_candidates = load_page_candidates(db, client, today=today)
    for ranked_pages, actions in (
        (rank_for_traffic(page_candidates), TRAFFIC_ACTIONS),
        (rank_for_leads(page_candidates), LEAD_ACTIONS),
    ):
        for candidate in ranked_pages:
            if is_excluded(candidate.url, exclusions) or not classify_page_url(candidate.url).eligible_for_growth_action:
                continue
            findings.extend(found for rule in actions if (found := rule(candidate)) is not None)
            found = prescribe_page(candidate, actions=actions)
            if found is not None:
                prescriptions.append(found)

    constraint_branch = next(
        (b for b in Branch if b.value == triage.constraint), None
    )
    from app.services.watchlist import read as read_watchlist
    for watched in read_watchlist(db, client):
        observation = watched.get("observation") or {}
        observed_on = observation.get("observed_on")
        if (watched["kind"] != "prompt" or watched["state"] != "existing"
                or not observed_on or observed_on > today.isoformat()
                or not (observation.get("brand_cited") is False or observation.get("brand_mentioned") is False)):
            continue
        findings.append(Prescription(
            action_id="G-1", title="Review the answer and citation gap",
            branch=Branch.VISIBILITY, target_url=watched["target_url"], term=watched["text"],
            score=0, effort_min=60,
            why=f"The observed answer for this selected prompt has a brand mention or citation gap. Review the response and source type before choosing a page change.",
            done_when="The brief names a verified answer gap and selected intervention, or records why an on-site change is not justified.",
            metric="Prompt mention and citations, checked on the same engine and prompt set",
            metric_key="decision",
            evidence=(f"Prompt: {watched['text']}", f"Provider: {watched.get('provider') or 'unspecified'}; observed: {observed_on}",
                      f"Observation: {observation}", "This observation does not establish that an on-site edit will win a citation."),
            steps=("Review the captured answer and cited sources.", "Choose and specify the answer or source improvement using verified facts.", "Recheck the same prompt and engine after the change."),
        ))
    by_branch: dict[Branch, list] = {}
    for prescription in prescriptions:
        by_branch.setdefault(prescription.branch, []).append(prescription)

    plan = fill_slots(
        slots=slots,
        constraint=constraint_branch,
        branches=list(triage.branches),
        prescriptions_by_branch=by_branch,
    )

    # ── The retainer pools ───────────────────────────────────────────────
    #
    # Updating existing content and writing new pages are bought every
    # month, whatever the constraint says, so they are their own pools
    # against their own allowances rather than competing for the growth
    # slots. The growth plan fills first and its pages are reserved: one
    # page prescribed both a growth action and a refresh in the same month
    # is two briefs, two Teamwork tasks and one confused writer.
    taken = {
        slot.prescription.target_url
        for slot in plan.filled
        if slot.prescription.target_url
    }
    previous_record = db.query(MonthlyRecord).filter(
        MonthlyRecord.client_id == client.id, MonthlyRecord.month == month,
    ).one_or_none()
    if previous_record and previous_record.record.get("plan_review"):
        review = previous_record.record["plan_review"]
        approved = review if review.get("approved_at") else next(iter(reversed(review.get("versions", []))), {})
        taken |= {x["target_url"] for x in approved.get("items", []) if x.get("target_url")}
    open_this_month = allowances.slots_open_in(month)
    closed_reason = (
        f"{allowances.tier_name} buys this quarterly, and this is not the "
        "first month of the quarter."
    )

    update_plan = fill_pool(
        slots=allowances.update_allowance if open_this_month else 0,
        prescriptions=[
            found
            for candidate in rank_for_updates(page_candidates)
            if not is_excluded(candidate.url, exclusions)
            and (found := prescribe_page(candidate, actions=UPDATE_ACTIONS)) is not None
        ],
        reserved_urls=taken,
        empty_reason=(
            "No page has lost enough ground to be worth a refresh this month."
            if open_this_month
            else closed_reason
        ),
    )
    taken |= {
        slot.prescription.target_url
        for slot in update_plan.filled
        if slot.prescription.target_url
    }

    # New pages, against the content allowance. They have no URL to reserve,
    # so the one-page-one-job rule cannot reach them; a term is their
    # identity, and `fold_variants` has already made it one page per subject.
    gap_scan = scan_term_gaps(db, client)
    demand_scan = scan_demand_gaps(db, client)
    # A demand gap that is the same subject as a tracked gap is that gap seen
    # from the other side: one page, prescribed once, by the tracked term.
    tracked_words = [content_words(gap.term) for gap in gap_scan.gaps]
    new_demand = [
        gap
        for gap in rank_demand(demand_scan.gaps)
        if not any(
            (words := content_words(gap.term)) and (words <= tw or tw <= words)
            for tw in tracked_words
        )
    ]
    content_prescriptions = [
        found
        for found in (
            [prescribe_term(gap) for gap in rank_for_content(gap_scan.gaps)]
            + [prescribe_demand(gap) for gap in new_demand]
        )
        if found is not None
    ]
    # A deliberately planned page is a human strategy decision, not an
    # inferred demand gap. Prompt-led pages need no invented search volume.
    planned_notes = set()
    for watched in read_watchlist(db, client):
        if watched["state"] != "planned" or not watched.get("note"):
            continue
        note_key = watched["note"].strip().lower()
        if note_key in planned_notes:
            continue
        planned_notes.add(note_key)
        content_prescriptions.append(Prescription(
            action_id="C-P", title=f"Create the planned page for “{watched['text']}”",
            branch=Branch.VISIBILITY, target_url="", term=watched["text"],
            score=0, effort_min=180, why=f"A person selected this page in the strategic watchlist: {watched['note']}",
            done_when="The reviewed page brief is implemented, published, mapped to its watchlist items and annotated.",
            metric="Manual check of the selected keyword or prompt intent", metric_key="decision",
            evidence=(f"Watchlist: {watched['kind']} — {watched['text']}", f"Planned page: {watched['note']}", "No keyword-volume estimate is required for this human-selected page."),
            steps=("Confirm the audience, intent and planned page against the strategy.", watched["note"], "Publish, record the final URL and update the watchlist target."),
        ))
    # One prize scale for both: searches a month the page could compete for.
    content_prescriptions.sort(key=lambda p: (-p.score, p.term or ""))
    empty_content = gap_scan.explain_empty()
    if not gap_scan.blocked and demand_scan.summary:
        d = demand_scan.summary
        empty_content += (
            f" Search Console showed {d.get('demand_queries', 0)} queries in the last "
            f"{LOOKBACK_DAYS} days; {d.get('demand_gaps', 0)} are demand with no page "
            f"and a price, {d.get('demand_unpriced', 0)} are waiting for a price."
        )
        if d.get("competitor_keywords"):
            empty_content += (
                f" The closest competitors rank in the top ten for "
                f"{d['competitor_keywords']} terms; {d.get('competitor_gaps', 0)} have "
                "no page on this site and are not tracked."
            )
    content_plan = fill_pool(
        slots=allowances.content_allowance if open_this_month else 0,
        prescriptions=content_prescriptions,
        empty_reason=empty_content if open_this_month else closed_reason,
    )

    return {
        "review_required": True,
        "recommendation_version": 3,
        "growth_capacity": allowances.growth_action_allowance,
        "findings": [
            _candidate_row(client, month, Considered(p, reason="Review against the client strategy."), today)
            for p in findings
        ],
        "client": client.slug,
        "client_name": client.client_name,
        "domain": client.domain,
        "month": month,
        "run_saved_at": datetime.now(timezone.utc).isoformat(),
        "data_through": gsc_newest.isoformat() if gsc_newest else None,
        "plan": (allowances.tier_name or "launch").lower(),
        "action_slots": slots,
        "constraint": triage.constraint,
        "reason_text": triage.reason_text,
        "override": triage.override,
        # What the tests produced, kept beside what a person chose. A record
        # that showed only the override could not be read back as a
        # disagreement, and the disagreement is the interesting part.
        **(
            {
                "engine_constraint": engine_said,
                "override_reason": override.reason,
            }
            if override is not None and triage.override == "manual"
            else {}
        ),
        "held_since": _held_since(db, client, month, triage.constraint),
        "confidence": confidence,
        "confidence_reasons": confidence_reasons,
        "measurements": measure_outcomes(db, client, end=today),
        "branches": [
            {
                "branch": branch.branch.value,
                "status": branch.status.value,
                "headline_test": branch.headline_test,
                "display": branch.display,
                "missing": list(branch.missing),
                "tests": [
                    {
                        "id": test.id,
                        "name": test.name,
                        "metric_label": test.metric_label,
                        "value": test.value,
                        "pass_line": test.pass_line,
                        "direction": test.direction,
                        "unit": test.unit,
                        "status": test.status.value,
                        "evidence": test.evidence,
                        **({"display": test.display} if test.display else {}),
                        **({"missing": test.missing} if test.missing else {}),
                    }
                    for test in branch.tests
                ],
            }
            for branch in triage.branches
        ],
        "actions": [
            _slot_row(client, month, slot, today)
            for slot in plan.filled
        ],
        "empty_slots": [
            {"slot": empty.slot, "reason": empty.reason} for empty in plan.empty
        ],
        # Incidents take no slot and do not change the constraint: a site
        # that stopped recording leads has a broken tag, not a conversion
        # problem. They are reported beside the plan so the plan is not read
        # as if the site were working.
        "incidents": [
            incident.as_dict()
            for incident in check_incidents(
                read_incident_signals(db, client, today=today),
                month=month,
                slug=client.slug,
            )
        ],
        # Retainer work, kept apart from the growth slots because it is
        # inside the monthly fee and they are not.
        "updates": [_slot_row(client, month, slot, today) for slot in update_plan.filled],
        "update_slots": allowances.update_allowance if open_this_month else 0,
        "empty_update_slots": [
            {"slot": empty.slot, "reason": empty.reason} for empty in update_plan.empty
        ],
        "update_candidates": [
            _candidate_row(client, month, c, today) for c in update_plan.considered
        ],
        # New pages, against the content allowance.
        "new_content": [_slot_row(client, month, slot, today) for slot in content_plan.filled],
        "content_slots": allowances.content_allowance if open_this_month else 0,
        "empty_content_slots": [
            {"slot": empty.slot, "reason": empty.reason} for empty in content_plan.empty
        ],
        "content_candidates": [
            _candidate_row(client, month, c, today) for c in content_plan.considered
        ],
        # What the scan checked, so an empty pool can say what it looked at.
        "content_scan": {
            **gap_scan.summary,
            **demand_scan.summary,
            **({"blocked": gap_scan.blocked} if gap_scan.blocked else {}),
        },
        "not_this_month": list(plan.not_this_month),
        # Everything the engine weighed, so a plan can be argued with. The
        # slotted ones are in here too, marked — one list to read rather
        # than two to reconcile.
        "candidates": [
            _candidate_row(client, month, c, today) for c in plan.considered
        ],
        "data_gaps": [
            {"input": text, "status": "missing"} for text in sorted(set(blocked_inputs))
        ]
        + [
            {"input": f"{a.action_id}: {a.reason}", "status": "missing"}
            for a in BLOCKED_ACTIONS
        ],
        "previous_results": previous_results(
            db, client, month, previous=_previous_month(month)
        ),
        "excluded_pages": [
            {"url_pattern": x.url_pattern, "reason": x.reason} for x in exclusions
        ],
        #: Targets dropped because their page is excluded. Said rather than
        #: left as a silent absence.
        "excluded_targets": inputs.excluded,
    }


def save_record(
    db: Session,
    client: Client,
    *,
    today: date | None = None,
    month: str | None = None,
) -> MonthlyRecord:
    """Run the engine and store the month's record, replacing any earlier one.

    One plan a month: re-running corrects that month's answer rather than
    adding a second one. Workflow state lives in `engine_actions`, keyed by a
    uid that survives the replacement, so an assignment made before a re-run
    is not lost by it.

    `month` runs a month other than the one we are in — the usual case, since
    a month is reviewed once it has finished. It is judged as of its last day,
    so every month-to-date measure covers the whole month rather than the few
    days elapsed in the month somebody happens to be sitting in.
    """
    today = as_of(month, today=today) if month else (today or date.today())
    from app.services.automatic_keyword_map import build as build_map
    map_summary = build_map(db, client)
    record = build_record(db, client, today=today)
    record["mapping_summary"] = map_summary
    month = record["month"]

    existing = (
        db.query(MonthlyRecord)
        .filter(MonthlyRecord.client_id == client.id, MonthlyRecord.month == month)
        .with_for_update().one_or_none()
    )
    if existing is None:
        existing = MonthlyRecord(id=uuid4(), client_id=client.id, month=month)
        db.add(existing)

    # A new assessment never overwrites a human decision or its approved versions.
    if existing.record and existing.record.get("plan_review"):
        record["plan_review"] = existing.record["plan_review"]

    existing.run_saved_at = datetime.now(timezone.utc)
    existing.data_through = (
        date.fromisoformat(record["data_through"]) if record["data_through"] else None
    )
    existing.constraint_name = record["constraint"]
    existing.held_since = record["held_since"]
    existing.confidence = record["confidence"]
    existing.record = record
    db.commit()
    db.refresh(existing)

    # The reading each action starts from, taken as-of the data the run saw.
    # Without it the check date arrives with nothing to compare against.
    captured = capture_before(db, client, existing)
    logger.info(
        "%s %s: %s (%s confidence), %d before-readings captured",
        client.slug, month, record["constraint"], record["confidence"], captured,
    )
    return existing


# ── Running it ──────────────────────────────────────────────────────────────

RUN_CHECKPOINT = "monthly_engine_run"


def _has_data(db: Session, client: Client) -> bool:
    """Whether there is anything to run on at all.

    Deliberately weak: a client whose sync has gone stale should get a
    Withheld record saying so, which is a more useful thing to open than an
    empty page. What this excludes is a client with no data whatsoever, where
    a run would produce noise rather than an answer.
    """
    return (
        _last_fact(db, FactGa4Traffic, FactGa4Traffic.date, client.id) is not None
        and _last_fact(db, FactGscPage, FactGscPage.date, client.id) is not None
    )


def maybe_run_month(db: Session, *, today: date | None = None) -> bool:
    """Run last month for every client with data, once a month.

    The month before, not the one we are in: a month is reviewed once it has
    finished. It replaces whatever is saved for that month rather than
    skipping it — a run made mid-month from partial data is exactly what this
    supersedes, and the engine reads the same facts every time, so there is
    no answer somebody preferred to protect. Assignments survive: they are
    keyed on the slot uid, and a slot whose action changed says so.
    """
    from sqlalchemy.exc import IntegrityError

    from app.core.settings import get_settings
    from app.models.scheduler import SchedulerCheckpoint

    settings = get_settings()
    if not settings.monthly_run_enabled:
        return False

    now = datetime.now(timezone.utc)
    today = today or now.date()
    if today.day < settings.monthly_run_day or now.hour < settings.monthly_run_hour_utc:
        return False

    checkpoint = (
        db.query(SchedulerCheckpoint)
        .filter(SchedulerCheckpoint.name == RUN_CHECKPOINT)
        .with_for_update()
        .one_or_none()
    )
    if checkpoint is None:
        checkpoint = SchedulerCheckpoint(name=RUN_CHECKPOINT, last_run_date=None)
        db.add(checkpoint)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return False

    last = checkpoint.last_run_date
    if last is not None and (last.year, last.month) == (today.year, today.month):
        db.rollback()
        return False

    # Claim the month before running anything, so a crash partway through
    # does not restart the whole portfolio on the next loop.
    checkpoint.last_run_date = today
    checkpoint.updated_at = now
    db.commit()

    month = _previous_month(month_key(today))
    ran = 0
    skipped = 0
    for client in db.query(Client).filter(Client.status.in_(WORKED_STATUSES)).all():
        if not _has_data(db, client):
            skipped += 1
            continue
        try:
            save_record(db, client, month=month, today=today)
            ran += 1
        except Exception:  # noqa: BLE001 — one bad client must not stop the rest
            db.rollback()
            logger.exception("Monthly run failed for %s", client.slug)

    logger.info(
        "Monthly run for %s: %d client(s) run, %d skipped for want of data",
        month, ran, skipped,
    )
    return True
