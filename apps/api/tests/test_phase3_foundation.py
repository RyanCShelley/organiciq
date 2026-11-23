"""Milestone 1 verification tests for Phase 3 shared backend foundation."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

import httpx

from app.decisions import action_context as ac
from app.decisions.checklists import checklist_for
from app.decisions.provisional import suggest as provisional_suggest
from app.integrations import dataforseo
from app.models.annotation import Annotation, AnnotationType
from app.models.client_focus import ClientFocus
from app.models.crawl import CRAWL_SOURCE_FIRST_PARTY, FactCrawlPageSnapshot
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.seranking import FactSerpFeature
from app.schema_tools import llm
from app.services import content_optimizer, ctr_titles, growth_action as ga, page_diagnostic as pd, part_tools, serp_features, task_verify, teamwork_subtasks
from tests.conftest import client_header
from tests.test_growth_action import BLOG, COLL, PROD, SEP, crawled, gsc, reading, sug, watch
from tests.test_growth_action_context import ids, read


def test_rejection_reasons_and_task_reject_lifecycle(client, db, client_a, admin_user):
    h = client_header(client_a.id, admin_user.email)
    res = client.get("/v2/engine/rejection-reasons", headers=h)
    assert res.status_code == 200
    reasons = res.json()["reasons"]
    assert len(reasons) == 8
    assert {r["key"] for r in reasons} == set(ac.REJECTION_REASONS)

    bad = client.post(
        "/v2/engine/tasks/reject",
        json={"page": PROD, "rejection_reason": "not_a_real_reason"},
        headers=h,
    )
    assert bad.status_code == 400

    rej = client.post(
        "/v2/engine/tasks/reject",
        json={
            "month": "2026-10",
            "page": PROD,
            "search": "natural sunscreen",
            "rule_id": "GA",
            "kind": "growth_action",
            "title": "Growth action: /products/spf-30",
            "rejection_reason": "wrong_intent",
            "rejection_note": "Informational query on a product page",
        },
        headers=h,
    )
    assert rej.status_code == 200, rej.text
    data = rej.json()
    assert data["status"] == "rejected"
    assert data["rejection_reason"] == "wrong_intent"
    assert data["rejection_reason_label"] == "Wrong search intent"
    assert data["rejection_note"] == "Informational query on a product page"
    assert data["rejected_by"] == admin_user.email
    assert data["rejected_at"] is not None

    plan = client.get("/v2/engine/tasks?month=2026-10", headers=h).json()
    assert plan["allowance"]["used"] == 0
    assert plan["work"]["parts"] == 0

    # Rejected task does not block building a fresh growth action on the same page/month
    gsc(db, client_a, "natural sunscreen", PROD, 500)
    db.commit()
    out = ga.build(
        db,
        client_a,
        SEP,
        "natural sunscreen",
        page=PROD,
        planned_month="2026-10",
        diagnose=read([sug("S-5")]),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert out["ok"] is True
    assert len(out["prior_rejections"]) == 1
    assert out["prior_rejections"][0]["rejection_reason"] == "wrong_intent"


def test_dedicated_page_type_checklists_and_focus_sorting():
    facts_done = {
        "h1": "Emergency Plumbing",
        "title": "Emergency Plumbing | Acme",
        "description": "24/7 licensed plumbers.",
        "word_count": 450,
        "schema_types": ["Service", "AggregateRating"],
        "has_faq": True,
        "conversion_elements": 2,
        "contact_only_in_footer": False,
        "sections": [{"heading": "Our Process", "has_list": True}],
    }
    svc = checklist_for("service", facts_done, focus="leads")
    assert len(svc) == 6
    by_id = {c["id"]: c for c in svc}
    assert by_id["CHK-SVC-2"]["status"] == "done"
    assert by_id["CHK-SVC-5"]["status"] == "done"
    assert by_id["CHK-SVC-6"]["status"] == "done"
    assert svc[0]["category"] == "conversion"

    loc = checklist_for("location", {"word_count": 50, "contact_only_in_footer": True, "schema_types": []})
    assert {c["id"]: c["status"] for c in loc}["CHK-LOC-3"] == "needed"

    cat = checklist_for("category", {"h1": "Mineral Sunscreens", "schema_types": ["CollectionPage"], "sections": [{"heading": "Compare", "has_table": True}]})
    assert {c["id"]: c["status"] for c in cat}["CHK-CAT-3"] == "done"
    assert {c["id"]: c["status"] for c in cat}["CHK-CAT-5"] == "done"

    home = checklist_for("homepage", {"h1": "Acme Co", "word_count": 300, "schema_types": ["Organization", "WebSite"]})
    assert {c["id"]: c["status"] for c in home}["CHK-HOME-5"] == "done"
    assert checklist_for("article", facts_done) == []


def test_plain_diagnose_applies_intent_page_type_fit_and_suppresses_mismatched_suggestions(client, db, client_a, admin_user, monkeypatch):
    url = f"https://{client_a.domain}/services/roof-repair"
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=date(2026, 8, 10),
            query="how to fix roof leak",
            raw_url=url,
            normalized_url=url,
            country="usa",
            device="DESKTOP",
            impressions=600,
            clicks=3,
            ctr=0,
            average_position=6.0,
        )
    )
    db.add(
        FactSerpFeature(
            client_id=client_a.id,
            pulled_on=date.today(),
            keyword="how to fix roof leak",
            item_types=["organic", "people_also_ask"],
            holders={},
            results=[{"rank": 1, "url": "https://r.example/a", "domain": "r.example", "title": "Guide", "snippet": "..."}],
            questions=["How long does a roof patch last?"],
            reading=reading("informational"),
        )
    )
    db.commit()

    html = "<html><head><title>Roof Repair</title></head><body><h1>Roof Repair Service</h1><p>Licensed roofers.</p></body></html>"

    async def fetch(u):
        return pd.Fetched(200, u, {}, html)

    monkeypatch.setattr(pd, "_fetch", fetch)
    h = client_header(client_a.id, admin_user.email)
    res = client.post(
        "/v2/engine/diagnose",
        json={"month": "2026-09", "selections": [{"search": "how to fix roof leak", "page": url}]},
        headers=h,
    )
    assert res.status_code == 200
    diag = res.json()["results"][0]
    ctx = diag["context"]
    assert ctx["page_type"]["type"] == "service"
    assert ctx["intent"]["intent"] == "informational"
    assert ctx["fit"]["level"] == "low"
    assert len(ctx["checklist"]) == 6
    # Low-fit informational query on a service page suppresses P-1 / S-2 into skipped_suggestions
    s_ids = [s["id"] for s in diag["suggestions"]]
    assert "P-1" not in s_ids
    assert "MC-1" in s_ids
    assert any(k["id"] == "P-1" for k in diag["skipped_suggestions"])

    # diagnose-page accepts focus="visibility" and defaults to active ClientFocus when omitted
    db.add(ClientFocus(client_id=client_a.id, month=date(2026, 10, 1), focus="visibility"))
    db.commit()
    dp = client.post("/v2/engine/diagnose-page", json={"month": "2026-09", "pages": [url]}, headers=h)
    assert dp.status_code == 200
    assert dp.json()["focus"] == "visibility"
    assert dp.json()["results"][0]["context"]["page_type"]["type"] == "service"


def test_focus_driven_ordering_for_leads_traffic_and_visibility(db, client_a):
    gsc(db, client_a, "buy spf 30 sunscreen", PROD, 900)
    db.add(ClientFocus(client_id=client_a.id, month=date(2026, 10, 1), focus="leads"))
    db.commit()

    extras = [
        {"id": "L-S2", "title": "Link to conversion page", "why": "w", "steps": ["Add CTA"], "evidence": []},
        {"id": "F-1", "title": "Remove friction", "why": "w", "steps": ["Shorten form"], "evidence": []},
    ]
    leads_out = ga.build(
        db,
        client_a,
        SEP,
        "spf 30 sunscreen",
        page=PROD,
        planned_month="2026-10",
        diagnose=read([sug("S-1"), sug("MC-1")]),
        evidence_for=lambda s, u: {},
        extra_suggestions=extras,
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert leads_out["focus"] == "leads"
    assert [p["id"] for p in leads_out["parts"]] == ["F-1", "L-S2", "MC-1", "IM-1", "S-1"]

    traffic_out = ga.build(
        db,
        client_a,
        SEP,
        "spf 30 sunscreen",
        page=PROD,
        focus="traffic",
        diagnose=read([sug("S-1"), sug("MC-1")]),
        evidence_for=lambda s, u: {},
        extra_suggestions=extras,
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert traffic_out["focus"] == "traffic"
    assert [p["id"] for p in traffic_out["parts"]] == ["MC-1", "IM-1", "S-1", "L-S2", "F-1"]


def test_faq_paa_fallback_and_mc1_and_tool_mapping(db, client_a):
    assert part_tools.tool_for("FQ-1")["key"] == "inlinks"
    assert part_tools.tool_for("MC-1")["key"] == "ctr"
    assert "MC-1" in task_verify._CHECKS

    gsc(db, client_a, "natural sunscreen", BLOG, 1000, clicks=5, position=8.0)
    crawled(db, client_a, "https://shop.example/faq", "Common Questions")
    db.commit()

    # PAA fallback works when winners_for is None and outline is absent
    out = ga.build(
        db,
        client_a,
        SEP,
        "natural sunscreen",
        page=BLOG,
        diagnose=read([sug("S-1")], facts={"schema_types": ["Article"]}),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("informational"), "questions": ["Is mineral sunscreen reef safe?"]},
        winners_for=None,
    )
    s2 = next(p for p in out["parts"] if p["id"] == "S-2")
    assert "Is mineral sunscreen reef safe?" in " ".join(s2["steps"])

    # MC-1 fires in provisional.suggest for position 4..20 underperforming CTR and dedupes against S-5
    parsed = pd.parse_page(url=PROD, body="<html><head><title>SPF 30</title><meta name='description' content='Short'></head><body><h1>SPF 30</h1><p>Zinc.</p></body></html>", headers={})
    facts = pd.facts_from(PROD, parsed)
    sug_out = provisional_suggest(
        search="spf 30",
        url=PROD,
        row={"position": 8.0, "impressions": 500, "clicks": 2},
        parsed=parsed,
        facts=facts,
        evidence={"page_queries": [{"query": "mineral spf 30", "impressions": 300, "clicks": 1, "position": 8.0}], "competing_pages": 1, "donors": []},
        serp_questions=["Does SPF 30 leave a white cast?"],
    )
    sug_ids = [s["id"] for s in sug_out["suggestions"]]
    assert "MC-1" in sug_ids and "S-5" not in sug_ids and "S-2" in sug_ids
    mc1 = next(s for s in sug_out["suggestions"] if s["id"] == "MC-1")
    assert "Title now (6 chars" in " ".join(mc1["steps"])
    assert "Meta description now (5 chars" in " ".join(mc1["steps"])


def test_custom_steps_style_notes_page_history_and_wider_serps(client, db, client_a, admin_user, monkeypatch):
    h = client_header(client_a.id, admin_user.email)

    # Style notes CRUD
    patched_client = client.patch(
        f"/clients/{client_a.id}",
        json={"style_notes": "Use calm, clinical language. Never use exclamation marks."},
        headers=h,
    )
    assert patched_client.status_code == 200
    assert patched_client.json()["style_notes"] == "Use calm, clinical language. Never use exclamation marks."

    # Verify style_notes injected into ctr_titles and content_optimizer prompts
    ctr_prompt = ctr_titles.build_prompt(
        url=PROD,
        brand="Shop",
        detail={"title": "SPF 30", "description": "Sunscreen", "searches": []},
        h1="SPF 30",
        content="Zinc sunscreen.",
        pattern={"suffix": None, "typical_length": 40},
        start="2026-09-01",
        end="2026-09-30",
        style_notes=patched_client.json()["style_notes"],
    )
    assert "Never use exclamation marks" in ctr_prompt
    assert '"descriptions"' in ctr_prompt

    opt_prompt = content_optimizer.build_prompt(
        "opening",
        url=PROD,
        brand="Shop",
        detail={"title": "SPF 30", "searches": []},
        spot={"h1": "SPF 30", "opening": "Old opening."},
        text="Old opening.",
        start="2026-09-01",
        end="2026-09-30",
        terms=[],
        style_notes=patched_client.json()["style_notes"],
    )
    assert "Never use exclamation marks" in opt_prompt

    # Custom steps update on saved EngineTask
    created = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-10",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "spf 30",
            "page": PROD,
            "title": "Grow SPF 30",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
        },
        headers=h,
    ).json()["task"]
    updated = client.patch(
        f"/v2/engine/tasks/{created['id']}",
        json={
            "steps": ["# 1. Rewrite the meta for clicks", "Update title", "# 2. Add trust badges", "Place badge by CTA"],
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "CUSTOM", "name": "Add trust badges", "custom": True},
            ],
        },
        headers=h,
    )
    assert updated.status_code == 200
    u_task = updated.json()
    assert len(u_task["steps"]) == 4
    assert u_task["parts"][1]["custom"] is True
    assert len(teamwork_subtasks.from_steps(u_task["steps"], growth=True)) == 2

    # Page history aggregation
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 10, 15),
            raw_url=PROD,
            normalized_url=PROD,
            indexable=True,
            title="SPF 30",
            description="Mineral sunscreen",
            word_count=250,
            content_changed_on=date(2026, 10, 15),
            previous_replaced_on=date(2026, 10, 15),
            paragraphs=[{"heading": "Intro", "text": "New copy."}],
            previous_paragraphs=[{"heading": "Intro", "text": "Old copy."}],
        )
    )
    db.add(
        Annotation(
            client_id=client_a.id,
            date=date(2026, 10, 16),
            annotation_type=AnnotationType.CONTENT_UPDATED,
            description="Updated opening paragraph",
            page_url=PROD,
        )
    )
    db.commit()
    hist = client.get("/v2/engine/page-history", params={"page": PROD}, headers=h)
    assert hist.status_code == 200
    hdata = hist.json()
    assert len(hdata["crawl_changes"]) == 1
    assert hdata["crawl_changes"][0]["diff_summary"]["added_count"] == 1
    assert len(hdata["tasks"]) == 1
    assert len(hdata["annotations"]) == 1

    # Wider DataForSEO SERPs: untracked GSC opportunity + on-demand /serp/pull
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=date.today(),
            query="mineral sunscreen for toddlers",
            raw_url=PROD,
            normalized_url=PROD,
            country="usa",
            device="DESKTOP",
            impressions=250,
            clicks=4,
            ctr=0,
            average_position=12.0,
        )
    )
    db.commit()
    terms = serp_features.terms_to_pull(db, client_a, limit=12)
    assert "mineral sunscreen for toddlers" in terms

    monkeypatch.setattr(dataforseo, "configured", lambda: True)
    monkeypatch.setattr(dataforseo, "keyword_overview", lambda *a, **k: [])
    monkeypatch.setattr(
        dataforseo,
        "fetch",
        lambda kw, **k: dataforseo.SerpFeatures(
            keyword=kw,
            item_types=("organic", "people_also_ask"),
            organic=({"rank": 1, "url": "https://a.example", "domain": "a.example", "title": "T", "snippet": "S"},),
            questions=("Is mineral sunscreen safe for toddlers?",),
        ),
    )
    llm_calls: list[str] = []
    monkeypatch.setattr(
        llm,
        "call",
        lambda depth, prompt, max_tokens=1800: (
            llm_calls.append(depth),
            json.dumps(
                {
                    "primary": "informational",
                    "secondary": None,
                    "mixed": False,
                    "confidence": "high",
                    "searcher_goal": "Learn whether mineral sunscreen is safe for toddlers.",
                    "results": [{"rank": 1, "content_type": "article or blog post", "content_style": "guide"}],
                    "evidence": ["Top ranking result is a pediatric guide."],
                    "uncertainty": None,
                    "label_disagreement": None,
                    "consumer_need": None,
                    "content_to_match": "Guide",
                }
            ),
            20,
            15,
        )[1:],
    )
    pulled = client.post("/v2/engine/serp/pull", json={"search": "mineral sunscreen for toddlers"}, headers=h)
    assert pulled.status_code == 200
    assert llm_calls == ["quick"]
    pdata = pulled.json()
    assert pdata["search"] == "mineral sunscreen for toddlers"
    assert pdata["questions"] == ["Is mineral sunscreen safe for toddlers?"]
    assert pdata["reading"]["intent"] == "informational"
    assert len(pdata["results"]) == 1

    got = client.get("/v2/engine/serp", params={"search": "mineral sunscreen for toddlers"}, headers=h)
    assert got.status_code == 200
    assert got.json()["questions"] == ["Is mineral sunscreen safe for toddlers?"]
