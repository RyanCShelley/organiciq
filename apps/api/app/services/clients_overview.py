from __future__ import annotations

from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import and_, case, func, not_, or_, true, tuple_
from sqlalchemy.orm import Session, joinedload

from app.core.client_scope import list_accessible_client_ids
from app.core.security import AuthUser
from app.models.client import Client
from app.models.config import ConversionDefinition, LeadExclusion, OrganicChannel
from app.models.ga4 import FactGa4Event, FactGa4Traffic
from app.models.gsc import FactGscDaily
from app.schemas.v2_overview import (
    ClientOverviewItemOut,
    ClientsOverviewOut,
    ClientsOverviewWindowOut,
)
from app.services import lead_exclusions, lead_goals
from app.services.plan_allowances import resolve_plan_allowances


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 1)


def _lead_label_for(business_model: str | None) -> Literal["leads", "orders", "conversions"]:
    if business_model == "ecommerce":
        return "orders"
    if business_model == "both":
        return "conversions"
    return "leads"


def _plan_label_for(client: Client) -> str | None:
    if client.service_mode == "consulting":
        return "Consulting"
    if client.tier is not None:
        return f"{resolve_plan_allowances(client, client.tier).tier_name} plan"
    return None


def build_clients_overview(
    db: Session,
    user: AuthUser,
    *,
    as_of: date | None = None,
) -> ClientsOverviewOut:
    cur_end = as_of or (date.today() - timedelta(days=1))
    cur_start = cur_end - timedelta(days=29)
    prev_end = cur_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=29)

    window = ClientsOverviewWindowOut(
        from_date=cur_start,
        to_date=cur_end,
        previous_from=prev_start,
        previous_to=prev_end,
        days=30,
    )

    accessible = list_accessible_client_ids(db, user)
    if accessible is not None and not accessible:
        return ClientsOverviewOut(window=window, clients=[])

    q = (
        db.query(Client)
        .options(joinedload(Client.tier), joinedload(Client.group))
        .order_by(Client.client_name.asc())
    )
    if accessible is not None:
        q = q.filter(Client.id.in_(accessible))
    clients = q.all()
    if not clients:
        return ClientsOverviewOut(window=window, clients=[])

    client_ids = [c.id for c in clients]

    # 1. GSC 30d & prior 30d (sum across all gsc_site_url properties)
    gsc_in_cur = and_(FactGscDaily.date >= cur_start, FactGscDaily.date <= cur_end)
    gsc_in_prev = and_(FactGscDaily.date >= prev_start, FactGscDaily.date <= prev_end)
    gsc_rows = (
        db.query(
            FactGscDaily.client_id,
            func.count(case((gsc_in_cur, 1))).label("cur_rows"),
            func.coalesce(func.sum(case((gsc_in_cur, FactGscDaily.impressions), else_=0)), 0).label("cur_imp"),
            func.coalesce(func.sum(case((gsc_in_cur, FactGscDaily.clicks), else_=0)), 0).label("cur_clk"),
            func.coalesce(
                func.sum(case((gsc_in_cur, FactGscDaily.average_position * FactGscDaily.impressions), else_=0)),
                0,
            ).label("cur_wpos"),
            func.count(case((gsc_in_prev, 1))).label("prev_rows"),
            func.coalesce(func.sum(case((gsc_in_prev, FactGscDaily.impressions), else_=0)), 0).label("prev_imp"),
            func.coalesce(
                func.sum(case((gsc_in_prev, FactGscDaily.average_position * FactGscDaily.impressions), else_=0)),
                0,
            ).label("prev_wpos"),
        )
        .filter(
            FactGscDaily.client_id.in_(client_ids),
            FactGscDaily.date >= prev_start,
            FactGscDaily.date <= cur_end,
        )
        .group_by(FactGscDaily.client_id)
        .all()
    )
    gsc_by_client = {row.client_id: row for row in gsc_rows}

    # 2. GSC freshness
    gsc_through_map: dict[UUID, date | None] = dict(
        db.query(FactGscDaily.client_id, func.max(FactGscDaily.date))
        .filter(FactGscDaily.client_id.in_(client_ids))
        .group_by(FactGscDaily.client_id)
        .all()
    )

    # 3. GA4 Traffic 30d & prior 30d
    ga_cur = and_(FactGa4Traffic.date >= cur_start, FactGa4Traffic.date <= cur_end)
    ga_prev = and_(FactGa4Traffic.date >= prev_start, FactGa4Traffic.date <= prev_end)
    is_org = FactGa4Traffic.channel == OrganicChannel.ORGANIC_SEARCH
    ga4_rows = (
        db.query(
            FactGa4Traffic.client_id,
            func.count(case((ga_cur, 1))).label("cur_rows"),
            func.coalesce(func.sum(case((ga_cur, FactGa4Traffic.sessions), else_=0)), 0).label("cur_total"),
            func.coalesce(
                func.sum(case((and_(ga_cur, is_org), FactGa4Traffic.sessions), else_=0)),
                0,
            ).label("cur_org"),
            func.count(case((ga_prev, 1))).label("prev_rows"),
            func.coalesce(
                func.sum(case((and_(ga_prev, is_org), FactGa4Traffic.sessions), else_=0)),
                0,
            ).label("prev_org"),
        )
        .filter(
            FactGa4Traffic.client_id.in_(client_ids),
            FactGa4Traffic.date >= prev_start,
            FactGa4Traffic.date <= cur_end,
        )
        .group_by(FactGa4Traffic.client_id)
        .all()
    )
    ga4_by_client = {row.client_id: row for row in ga4_rows}

    # 4. GA4 freshness
    ga4_through_map: dict[UUID, date | None] = dict(
        db.query(FactGa4Traffic.client_id, func.max(FactGa4Traffic.date))
        .filter(FactGa4Traffic.client_id.in_(client_ids))
        .group_by(FactGa4Traffic.client_id)
        .all()
    )

    # 5. Active ConversionDefinitions (business_model-aware)
    conv_defs = (
        db.query(
            ConversionDefinition.client_id,
            ConversionDefinition.event_name,
            ConversionDefinition.conversion_type,
        )
        .filter(
            ConversionDefinition.client_id.in_(client_ids),
            ConversionDefinition.active.is_(True),
            ConversionDefinition.conversion_type != "engagement",
        )
        .all()
    )
    defs_by_client: dict[UUID, list[tuple[str, str]]] = {}
    for cid, ev_name, conv_type in conv_defs:
        defs_by_client.setdefault(cid, []).append((ev_name, (conv_type or "").lower()))

    allowed_pairs: set[tuple[UUID, str]] = set()
    configured_client_ids: set[UUID] = set()
    for c in clients:
        c_defs = defs_by_client.get(c.id, [])
        if not c_defs:
            continue
        if c.business_model == "ecommerce":
            matched = [ev for ev, ct in c_defs if ct in ("ecommerce", "purchase", "order")]
            if not matched:
                matched = [ev for ev, ct in c_defs if ct in ("lead", "call")]
        elif c.business_model == "both":
            matched = [ev for ev, _ct in c_defs]
        else:
            matched = [ev for ev, ct in c_defs if ct in ("lead", "call")]

        for ev in matched:
            allowed_pairs.add((c.id, ev))
            configured_client_ids.add(c.id)

    # 6 & 7. LeadExclusions + FactGa4Event aggregation
    leads_by_client: dict[UUID, object] = {}
    if allowed_pairs:
        excl_by_client: dict[UUID, list] = {}
        for rule in (
            db.query(LeadExclusion)
            .filter(LeadExclusion.client_id.in_(list(configured_client_ids)))
            .all()
        ):
            clause = lead_exclusions._rule_clause(rule)
            if clause is not None:
                excl_by_client.setdefault(rule.client_id, []).append(clause)

        per_client_excl = [
            and_(FactGa4Event.client_id == cid, or_(*clauses))
            for cid, clauses in excl_by_client.items()
        ]
        not_excluded_batch = not_(or_(*per_client_excl)) if per_client_excl else true()

        ev_cur = and_(FactGa4Event.date >= cur_start, FactGa4Event.date <= cur_end)
        ev_prev = and_(FactGa4Event.date >= prev_start, FactGa4Event.date <= prev_end)
        lead_rows = (
            db.query(
                FactGa4Event.client_id,
                func.count(case((ev_cur, 1))).label("cur_rows"),
                func.coalesce(func.sum(case((ev_cur, FactGa4Event.event_count), else_=0)), 0).label("cur_leads"),
                func.count(case((ev_prev, 1))).label("prev_rows"),
                func.coalesce(func.sum(case((ev_prev, FactGa4Event.event_count), else_=0)), 0).label("prev_leads"),
            )
            .filter(
                tuple_(FactGa4Event.client_id, FactGa4Event.event_name).in_(list(allowed_pairs)),
                FactGa4Event.date >= prev_start,
                FactGa4Event.date <= cur_end,
                not_excluded_batch,
            )
            .group_by(FactGa4Event.client_id)
            .all()
        )
        leads_by_client = {row.client_id: row for row in lead_rows}

    from app.models.bing_stats import FactBingQueryStat
    from app.models.watchlist import WatchlistKeyword

    watchlist_client_ids: set[UUID] = {
        row[0]
        for row in db.query(WatchlistKeyword.client_id)
        .filter(WatchlistKeyword.client_id.in_(client_ids))
        .distinct()
        .all()
    }

    pillars_by_client = {c.id: lead_goals.current_pillar_goals(c, on=cur_end) for c in clients}
    bing_client_ids = [
        c.id for c in clients if pillars_by_client[c.id]["monthly_gsc_impressions"]
    ]
    bing_by_client: dict[UUID, tuple[int, int]] = {}
    if bing_client_ids:
        bing_rows = (
            db.query(
                FactBingQueryStat.client_id,
                func.coalesce(func.sum(FactBingQueryStat.impressions), 0).label("impressions"),
                func.coalesce(func.sum(FactBingQueryStat.clicks), 0).label("clicks"),
            )
            .filter(
                FactBingQueryStat.client_id.in_(bing_client_ids),
                FactBingQueryStat.week_start >= cur_start,
                FactBingQueryStat.week_start <= cur_end,
            )
            .group_by(FactBingQueryStat.client_id)
            .all()
        )
        bing_by_client = {
            row.client_id: (int(row.impressions or 0), int(row.clicks or 0))
            for row in bing_rows
        }

    items: list[ClientOverviewItemOut] = []
    for c in clients:
        # GSC extraction
        g_row = gsc_by_client.get(c.id)
        if g_row is None or int(g_row.cur_rows or 0) == 0:
            impressions = clicks = avg_position = avg_position_change = impressions_change_pct = None
        else:
            cur_imp = float(g_row.cur_imp or 0)
            cur_clk = float(g_row.cur_clk or 0)
            cur_wpos = float(g_row.cur_wpos or 0)
            impressions = round(cur_imp)
            clicks = round(cur_clk)
            avg_position = round(cur_wpos / cur_imp, 1) if cur_imp > 0 else None
            prev_imp = float(g_row.prev_imp or 0)
            prev_wpos = float(g_row.prev_wpos or 0)
            prev_avg_pos = (prev_wpos / prev_imp) if prev_imp > 0 and int(g_row.prev_rows or 0) > 0 else None
            avg_position_change = (
                round(prev_avg_pos - avg_position, 1)
                if avg_position is not None and prev_avg_pos is not None
                else None
            )
            impressions_change_pct = (
                _pct_change(cur_imp, prev_imp)
                if int(g_row.prev_rows or 0) > 0
                else None
            )

        # GA4 Traffic extraction
        t_row = ga4_by_client.get(c.id)
        ga4_cur_rows = int(t_row.cur_rows or 0) if t_row is not None else 0
        ga4_prev_rows = int(t_row.prev_rows or 0) if t_row is not None else 0
        if t_row is None or ga4_cur_rows == 0:
            total_sessions = organic_sessions = organic_change_pct = None
        else:
            cur_org = float(t_row.cur_org or 0)
            total_sessions = round(float(t_row.cur_total or 0))
            organic_sessions = round(cur_org)
            organic_change_pct = (
                _pct_change(cur_org, float(t_row.prev_org or 0))
                if ga4_prev_rows > 0
                else None
            )

        # Leads extraction
        l_row = leads_by_client.get(c.id)
        lead_cur_rows = int(getattr(l_row, "cur_rows", 0) or 0)
        lead_prev_rows = int(getattr(l_row, "prev_rows", 0) or 0)
        if c.id not in configured_client_ids or (ga4_cur_rows == 0 and lead_cur_rows == 0):
            leads = None
            leads_change_pct = None
        else:
            cur_leads = int(getattr(l_row, "cur_leads", 0) or 0)
            prev_leads = int(getattr(l_row, "prev_leads", 0) or 0)
            leads = cur_leads
            leads_change_pct = (
                _pct_change(float(cur_leads), float(prev_leads))
                if (ga4_prev_rows > 0 or lead_prev_rows > 0)
                else None
            )

        bm = c.business_model if c.business_model in ("lead_gen", "ecommerce", "both") else None
        status_val = c.status.value if hasattr(c.status, "value") else str(c.status)
        pillar = pillars_by_client[c.id]
        cur_lead_goal = pillar["monthly_leads"]
        cur_impr_goal = pillar["monthly_gsc_impressions"]
        cur_clicks_goal = pillar["monthly_gsc_clicks"]
        cur_sess_goal = pillar["monthly_sessions"]
        bing_impr_cur, bing_clicks_cur = bing_by_client.get(c.id, (0, 0))
        if bing_impr_cur > 0:
            impressions = (impressions or 0) + bing_impr_cur
        if bing_clicks_cur > 0:
            clicks = (clicks or 0) + bing_clicks_cur

        missing_setup: list[str] = []
        if not (c.baseline_projection_json or {}).get("checkpoints"):
            missing_setup.append("No baseline")
        if c.id not in watchlist_client_ids:
            missing_setup.append("No watchlist")
        if c.id not in configured_client_ids:
            missing_setup.append("No conversions")
        if ga4_through_map.get(c.id) is None:
            missing_setup.append("No GA4 data")
        if gsc_through_map.get(c.id) is None:
            missing_setup.append("No GSC data")

        items.append(
            ClientOverviewItemOut(
                id=c.id,
                client_name=c.client_name,
                slug=c.slug,
                domain=c.domain,
                status=status_val,
                service_mode=c.service_mode,
                group_name=c.group.name if c.group else None,
                plan_label=_plan_label_for(c),
                business_model=bm,
                missing_setup=missing_setup,
                monthly_lead_goal=c.monthly_lead_goal,
                current_lead_goal=cur_lead_goal,
                lead_goal_progress_pct=(
                    round((leads / cur_lead_goal) * 100, 1)
                    if cur_lead_goal and leads is not None
                    else None
                ),
                impressions=impressions,
                clicks=clicks,
                avg_position=avg_position,
                avg_position_change=avg_position_change,
                impressions_change_pct=impressions_change_pct,
                current_impressions_goal=cur_impr_goal,
                impressions_goal_progress_pct=(
                    round((impressions / cur_impr_goal) * 100, 1)
                    if cur_impr_goal and impressions is not None
                    else None
                ),
                current_clicks_goal=cur_clicks_goal,
                total_sessions=total_sessions,
                organic_sessions=organic_sessions,
                organic_change_pct=organic_change_pct,
                current_sessions_goal=cur_sess_goal,
                sessions_goal_progress_pct=(
                    round((total_sessions / cur_sess_goal) * 100, 1)
                    if cur_sess_goal and total_sessions is not None
                    else None
                ),
                leads=leads,
                lead_label=_lead_label_for(bm),
                leads_change_pct=leads_change_pct,
                gsc_through=gsc_through_map.get(c.id),
                ga4_through=ga4_through_map.get(c.id),
            )
        )

    return ClientsOverviewOut(window=window, clients=items)
