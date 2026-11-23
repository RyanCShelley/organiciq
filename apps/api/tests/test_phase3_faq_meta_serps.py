"""Phase 3 tests: FAQ Enhancements, MC-1, Custom Steps, Page History, Style Notes & Wider SERPs."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from app.api.routers import v2_tasks
from app.core.settings import get_settings
from app.decisions.faq_links import find_faq_page
from app.integrations import dataforseo, teamwork
from app.models.annotation import Annotation, AnnotationResult, AnnotationType
from app.models.crawl import (
    CRAWL_SOURCE_FIRST_PARTY,
    FactCrawlInternalLink,
    FactCrawlPageSchema,
    FactCrawlPageSnapshot,
)
from app.models.decision import KeywordTarget
from app.models.engine_task import EngineTask
from app.models.gsc import FactGscQueryPage
from app.models.schema_tools import ContentModelRun, CtrTitleDraft
from app.models.seranking import FactSerKeyword, FactSerpFeature
from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.schema_tools import llm
from app.services import (
    content_optimizer,
    ctr_titles,
    growth_action as ga,
    page_diagnostic as pd,
    part_tools,
    search_signals,
    search_visibility,
    serp_features,
    task_verify,
    teamwork_subtasks,
)
from tests.conftest import auth_header, client_header
from tests.test_growth_action import BLOG, PROD, SEP, crawled, gsc, reading, sug
from tests.test_growth_action_context import read


# ── Area 5: FAQ Enhancements (PAA + Existing FAQ Page Check & FQ-1) ──────────


def test_growth_action_surfaces_paa_questions_when_winners_or_outline_is_absent(db, client_a):
    gsc(db, client_a, "mineral sunscreen", BLOG, 900, clicks=8, position=7.0)
    db.commit()

    # Case 1: winners_for is None
    out_no_winners = ga.build(
        db,
        client_a,
        SEP,
        "mineral sunscreen",
        page=BLOG,
        diagnose=read([sug("S-1")], facts={"schema_types": ["Article"]}),  # no outline
        evidence_for=lambda s, u: {
            "page_queries": [{"query": "is mineral sunscreen better for skin", "impressions": 80}],
        },
        signals_for=lambda s: {
            "reading": reading("informational"),
            "questions": ["Is mineral sunscreen safe daily?", "is mineral sunscreen safe daily?"],
        },
        winners_for=None,
    )
    s2 = next(p for p in out_no_winners["parts"] if p["id"] == "S-2")
    steps_joined = "\n".join(s2["steps"])
    assert "Is mineral sunscreen safe daily?" in steps_joined
    assert "is mineral sunscreen better for skin" in steps_joined
    assert steps_joined.lower().count("is mineral sunscreen safe daily?") == 1

    # Case 2: winners_for is provided, but facts["outline"] is absent -> winners_for skipped, PAA fallback runs
    called = []
    out_no_outline = ga.build(
        db,
        client_a,
        SEP,
        "mineral sunscreen",
        page=BLOG,
        diagnose=read(
            [sug("S-1")],
            facts={
                "schema_types": ["Article"],
                "has_faq": True,
                "outline": None,
            },
        ),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {
            "reading": reading("informational"),
            "questions": ["Does zinc oxide clog pores?"],
        },
        winners_for=lambda *a, **k: called.append(a) or {},
    )
    assert called == []
    s2_existing = next(p for p in out_no_outline["parts"] if p["id"] == "S-2")
    assert "Does zinc oxide clog pores?" in " ".join(s2_existing["steps"])
    assert s2_existing["name"] == "Add the missing questions to the FAQ"


def test_faq_page_discovery_by_url_title_or_schema_and_diagnose_fq1_wiring(client, db, client_a, admin_user, monkeypatch):
    from app.decisions.faq_links import find_faq_page

    assert part_tools.tool_for("FQ-1")["key"] == "inlinks"
    described = part_tools.describe([{"id": "FQ-1", "name": "Link to the site's FAQ page"}])
    assert described[0]["tool"] == "inlinks"
    assert part_tools.from_steps(["# 1. Link to the site's FAQ page"]) == [{"id": "FQ-1", "name": "Link to the site's FAQ page"}]

    target_page = f"https://{client_a.domain}/products/zinc-cream"
    help_faq = f"https://{client_a.domain}/help-center"

    # Unit checks for URL, title, schema, and self-skip in find_faq_page
    assert find_faq_page(db, client_a, {f"https://{client_a.domain}/faq": ""}, target_page)["id"] == "FQ-1"
    assert find_faq_page(db, client_a, {f"https://{client_a.domain}/faq": "FAQ"}, f"https://{client_a.domain}/faq") is None
    assert find_faq_page(db, client_a, {f"https://{client_a.domain}/questions-page": "Common Questions"}, target_page) is None
    assert find_faq_page(db, client_a, {f"https://{client_a.domain}/common-questions": "Common Questions"}, target_page)["id"] == "FQ-1"

    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 8, 25),
            raw_url=help_faq,
            normalized_url=help_faq,
            indexable=True,
            title="Support & Common Questions",
        )
    )
    # Also add FAQPage schema on /help-center so FAQPage schema discovery works even without /faq slug
    db.add(
        FactCrawlPageSchema(
            client_id=client_a.id,
            snapshot_date=date(2026, 8, 25),
            normalized_url=help_faq,
            syntax="json-ld",
            schema_type="FAQPage",
        )
    )
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 8, 25),
            raw_url=target_page,
            normalized_url=target_page,
            indexable=True,
            title="Zinc Cream",
        )
    )
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=date(2026, 8, 10),
            query="zinc cream",
            raw_url=target_page,
            normalized_url=target_page,
            country="usa",
            device="DESKTOP",
            impressions=600,
            clicks=5,
            ctr=0,
            average_position=8.0,
        )
    )
    db.add(
        FactSerpFeature(
            client_id=client_a.id,
            pulled_on=date.today(),
            keyword="zinc cream",
            item_types=["organic", "people_also_ask"],
            holders={},
            results=[{"rank": 1, "url": "https://r.example/z", "domain": "r.example", "title": "Zinc", "snippet": "..."}],
            questions=["Is zinc cream good for redness?"],
            reading=reading("transactional"),
        )
    )
    # Non-content (nav/footer) link does NOT suppress FQ-1
    link_row = FactCrawlInternalLink(
        client_id=client_a.id,
        source=CRAWL_SOURCE_FIRST_PARTY,
        snapshot_date=date(2026, 8, 25),
        from_url=target_page,
        to_url=help_faq,
        in_content=False,
    )
    db.add(link_row)
    db.commit()

    html = (
        "<html><head><title>Zinc Cream</title><meta name='description' content='Gentle zinc cream.'></head>"
        "<body><h1>Zinc Cream</h1><h2>Frequently Asked Questions</h2><h3>What is zinc cream?</h3><p>Skin barrier cream.</p></body></html>"
    )

    async def fetch(u):
        return pd.Fetched(200, u, {}, html)

    monkeypatch.setattr(pd, "_fetch", fetch)
    h = client_header(client_a.id, admin_user.email)

    diag = client.post(
        "/v2/engine/diagnose",
        json={"month": "2026-09", "selections": [{"search": "zinc cream", "page": target_page}]},
        headers=h,
    )
    assert diag.status_code == 200
    sugs = diag.json()["results"][0]["suggestions"]
    sug_ids = [s["id"] for s in sugs]
    assert "FQ-1" in sug_ids
    assert "S-2" in sug_ids  # existing FAQ still surfaces unanswered PAA question
    fq1 = next(s for s in sugs if s["id"] == "FQ-1")
    assert help_faq in fq1["steps"][0]

    # diagnose-page also includes FQ-1 when unlinked in-content
    dp = client.post("/v2/engine/diagnose-page", json={"month": "2026-09", "focus": "traffic", "pages": [target_page]}, headers=h)
    assert dp.status_code == 200
    assert "FQ-1" in [s["id"] for s in dp.json()["results"][0]["suggestions"]]

    # Once an in-content link exists, FQ-1 disappears from both diagnose and diagnose-page
    link_row.in_content = True
    db.commit()
    diag_after = client.post(
        "/v2/engine/diagnose",
        json={"month": "2026-09", "selections": [{"search": "zinc cream", "page": target_page}]},
        headers=h,
    )
    assert "FQ-1" not in [s["id"] for s in diag_after.json()["results"][0]["suggestions"]]


# ── Area 6a: "Rewrite the meta for clicks" (MC-1) & Meta Descriptions ────────


def test_mc1_tool_mapping_verification_and_ctr_descriptions(client, db, client_a, admin_user, monkeypatch):
    from app.decisions.provisional import suggest as provisional_suggest
    from app.ingestion.crawler.parse import parse_page

    assert part_tools.tool_for("MC-1")["key"] == "ctr"
    assert part_tools.from_steps(["# 1. Rewrite the meta for clicks"]) == [{"id": "MC-1", "name": "Rewrite the meta for clicks"}]
    assert task_verify._CHECKS["MC-1"] is task_verify._check_title

    # MC-1 triggers on page 2 (pos 14.0) with underperforming CTR and quotes title/desc lengths + recoverable clicks
    p2_url = f"https://{client_a.domain}/products/zinc-lotion"
    p2_html = "<html><head><title>Zinc Lotion</title><meta name='description' content='Old short description.'></head><body><h1>Zinc</h1><p>Body.</p></body></html>"
    parsed_p2 = parse_page(url=p2_url, body=p2_html, headers={})
    p2_sug = provisional_suggest(
        search="zinc lotion",
        url=p2_url,
        row={"position": 14.0, "impressions": 1200, "clicks": 1},
        parsed=parsed_p2,
        facts=pd.facts_from(p2_url, parsed_p2),
        evidence={"page_queries": [{"query": "mineral zinc lotion", "impressions": 400, "position": 14.0}], "competing_pages": 1, "donors": []},
    )
    mc1_p2 = next(s for s in p2_sug["suggestions"] if s["id"] == "MC-1")
    steps_txt = " ".join(mc1_p2["steps"])
    assert "Title now (11 chars" in steps_txt
    assert "Meta description now (22 chars" in steps_txt
    assert "recoverable clicks" in steps_txt

    url = f"https://{client_a.domain}/products/zinc-lotion"
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 11, 1),
            raw_url=url,
            normalized_url=url,
            status_code=200,
            indexable=True,
            title="Zinc Lotion",
            description="Old short description.",
            word_count=300,
        )
    )
    db.commit()

    h = client_header(client_a.id, admin_user.email)
    created = client.post(
        "/v2/engine/tasks",
        json={
            "month": "2026-11",
            "kind": "growth_action",
            "rule_id": "GA",
            "search": "zinc lotion",
            "page": url,
            "title": "Grow zinc lotion",
            "steps": ["# 1. Rewrite the meta for clicks", "Update title and meta description"],
            "parts": [{"id": "MC-1", "name": "Rewrite the meta for clicks"}],
        },
        headers=h,
    ).json()["task"]

    # Unchanged live page -> not_live
    async def same_page(u):
        return pd.Fetched(
            200,
            u,
            {},
            "<html><head><title>Zinc Lotion</title><meta name='description' content='Old short description.'></head><body><h1>Zinc</h1><p>Body</p></body></html>",
        )

    task_row = db.get(EngineTask, created["id"])
    not_live = task_verify.check_task(db, client_a, task_row, fetch=same_page)
    assert not_live["live"] == 0
    db.refresh(task_row)
    assert task_row.parts[0]["last_check"]["result"] == "not_live"

    # Updated meta description -> MC-1 verified live!
    async def updated_desc_page(u):
        return pd.Fetched(
            200,
            u,
            {},
            "<html><head><title>Zinc Lotion</title><meta name='description' content='Soothing mineral zinc lotion for sensitive skin with free shipping.'></head><body><h1>Zinc</h1><p>Body</p></body></html>",
        )

    live_res = task_verify.check_task(db, client_a, task_row, fetch=updated_desc_page)
    assert live_res["live"] == 1
    db.refresh(task_row)
    assert task_row.status == "shipped"
    assert task_row.parts[0]["status"] == "done"
    assert "meta description changed" in task_row.parts[0]["verified_how"]
    assert db.query(Annotation).filter(Annotation.client_id == client_a.id).count() == 1

    # ctr_titles.clean_descriptions + ctr_titles.run + GET /v2/ctr/page + GET /v2/ctr/title/{id}
    cleaned_descs, rec_idx = ctr_titles.clean_descriptions(
        {
            "descriptions": [
                {"description": "Old short description.", "serves": ["zinc lotion"], "why": "Same as current"},
                {"description": "Calm sensitive skin with mineral zinc lotion. Ships fast.", "serves": ["zinc lotion"], "why": "Benefit first"},
                {"description": "A" * 170, "serves": ["zinc lotion"], "why": "Too long test"},
            ],
            "recommended_description": 1,
        },
        "Old short description.",
    )
    assert len(cleaned_descs) == 2
    assert rec_idx == 0
    assert cleaned_descs[0]["too_long"] is False
    assert cleaned_descs[1]["too_long"] is True

    # Seed GSC for ctr_titles.run()
    today = date.today()
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=today - timedelta(days=2),
            query="zinc lotion",
            raw_url=url,
            normalized_url=url,
            country="usa",
            device="DESKTOP",
            impressions=600,
            clicks=3,
            ctr=0,
            average_position=11.0,
        )
    )
    client_a.style_notes = "Write calmly with zero hype."
    db.commit()

    captured_prompt: list[str] = []
    monkeypatch.setattr(
        llm,
        "call",
        lambda depth, prompt, max_tokens=6000: (
            captured_prompt.append(prompt),
            json.dumps(
                {
                    "diagnosis": "Snippet lacks skin-type specificity.",
                    "options": [
                        {"title": "Mineral Zinc Lotion for Sensitive Skin", "serves": ["zinc lotion"], "why": "Clear benefit"},
                        {"title": "Soothing Zinc Lotion | Client A", "serves": ["zinc lotion"], "why": "Brand trust"},
                    ],
                    "recommended": 0,
                    "descriptions": [
                        {"description": "Gentle mineral zinc lotion made for reactive skin. Read ingredients and order today.", "serves": ["zinc lotion"], "why": "Direct answer"},
                    ],
                    "recommended_description": 0,
                }
            ),
            100,
            80,
        )[1:],
    )
    monkeypatch.setattr(ctr_titles, "read_page", lambda u, d: pd.Fetched(200, u, {}, "<html><body><h1>Zinc Lotion</h1><p>Calm skin.</p></body></html>"))

    class _NoCloseSession:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def close(self):
            pass

    monkeypatch.setattr(ctr_titles, "SessionLocal", lambda: _NoCloseSession(db))
    draft = ctr_titles.start(db, client_a, url, "quick", today - timedelta(days=14), today, admin_user.email)
    ctr_titles.run(draft.id)

    assert len(captured_prompt) == 1
    assert "Write calmly with zero hype." in captured_prompt[0]

    polled = client.get(f"/v2/ctr/title/{draft.id}", headers=h)
    assert polled.status_code == 200
    pdata = polled.json()
    assert pdata["status"] == "done"
    assert pdata["titles"] == ["Mineral Zinc Lotion for Sensitive Skin", "Soothing Zinc Lotion | Client A"]
    assert len(pdata["options"]) == 2
    assert len(pdata["descriptions"]) == 1
    assert pdata["recommended_description"] == 0
    assert pdata["description_now"] == "Old short description."
    assert pdata["description_now_length"] == len("Old short description.")

    page_ctr = client.get(
        "/v2/ctr/page",
        params={"url": url, "from": (today - timedelta(days=14)).isoformat(), "to": today.isoformat()},
        headers=h,
    )
    assert page_ctr.status_code == 200
    assert page_ctr.json()["title_draft"]["descriptions"] == pdata["descriptions"]


# ── Area 6b: Custom Steps Persistence & Teamwork Subtasks ────────────────────


def test_custom_steps_persistence_part_merging_and_teamwork_subtasks(client, db, client_a, admin_user, monkeypatch):
    h = client_header(client_a.id, admin_user.email)
    client_a.teamwork_tasklist_id = "12345"
    db.commit()

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
    task_id = created["id"]

    # Mark part 0 done first, then PATCH steps + parts adding a CUSTOM part and keeping part 0 done
    client.patch(f"/v2/engine/tasks/{task_id}/parts/0", json={"done": True}, headers=h)
    patched = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={
            "steps": [
                "# 1. Rewrite the meta for clicks",
                "Update title",
                "# 2. Add dermatologist badge",
                "Place badge near primary CTA",
                "Link badge to clinical test summary",
            ],
            "parts": [
                {"id": "MC-1", "name": "Rewrite the meta for clicks"},
                {"id": "CUSTOM", "name": "Add dermatologist badge", "custom": True},
            ],
        },
        headers=h,
    )
    assert patched.status_code == 200, patched.text
    pt = patched.json()
    assert pt["parts"][0]["status"] == "done"
    assert pt["parts"][0]["custom"] is False
    assert pt["parts"][1]["id"] == "CUSTOM"
    assert pt["parts"][1]["custom"] is True
    assert pt["parts"][1]["tool"] is None

    # Also verify syncing parts from steps alone when parts is omitted
    synced = client.patch(
        f"/v2/engine/tasks/{task_id}",
        json={
            "steps": [
                "# 1. Rewrite the meta for clicks",
                "Update title",
                "# 2. Add dermatologist badge",
                "Place badge near primary CTA",
                "# 3. Add video demo",
                "Embed 30-second product walkthrough",
            ],
        },
        headers=h,
    )
    assert synced.status_code == 200
    assert [p["name"] for p in synced.json()["parts"]] == [
        "Rewrite the meta for clicks",
        "Add dermatologist badge",
        "Add video demo",
    ]
    assert synced.json()["parts"][2]["id"] == "CUSTOM"
    assert synced.json()["parts"][2]["custom"] is True

    # Custom part returns "cannot" in task_verify without crashing
    task_row = db.get(EngineTask, task_id)
    assert task_verify.verdict_for(task_row.parts[2], {}, text="", db=db, client=client_a, task=task_row)[0] == "cannot"

    # Teamwork subtasks include custom headings on send
    subs = teamwork_subtasks.from_steps(pt["steps"], growth=True)
    assert [s.name for s in subs] == ["1. Rewrite the meta for clicks", "2. Add dermatologist badge"]
    assert "Place badge near primary CTA" in subs[1].description

    created_subtasks: list[str] = []
    monkeypatch.setattr(teamwork, "configured", lambda: True)
    monkeypatch.setattr(teamwork, "create_task", lambda **kw: {"id": "tw-100", "url": "https://tw.example/100"})
    monkeypatch.setattr(teamwork, "create_subtask", lambda **kw: created_subtasks.append(kw["name"]) or {"id": f"sub-{len(created_subtasks)}", "url": ""})
    sent = client.post(f"/v2/engine/tasks/{task_id}/send", headers=h)
    assert sent.status_code == 200
    assert "2. Add dermatologist badge" in created_subtasks
    assert "3. Add video demo" in created_subtasks


# ── Area 6c: Page History & Client Style Notes ───────────────────────────────


def test_page_history_aggregates_crawl_diffs_shipped_and_rejected_tasks_and_annotations(
    client, db, client_a, client_b, admin_user
):
    page_url = f"https://{client_a.domain}/services/audit"
    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 10, 12),
            raw_url=page_url,
            normalized_url=page_url,
            indexable=True,
            title="SEO Audit Service",
            description="Full technical audit.",
            word_count=640,
            content_updated_on=date(2026, 10, 10),
            content_changed_on=date(2026, 10, 12),
            previous_replaced_on=date(2026, 10, 12),
            paragraphs=[{"heading": "Intro", "text": "Updated opening sentence."}, {"heading": "FAQ", "text": "New FAQ answer."}],
            previous_paragraphs=[{"heading": "Intro", "text": "Old opening sentence."}],
        )
    )
    db.add(
        EngineTask(
            client_id=client_a.id,
            month="2026-09",
            kind="growth_action",
            rule_id="GA",
            search="seo audit",
            page_url=page_url,
            title="Shipped GA",
            status="shipped",
            confirmed_by=admin_user.email,
            shipped_at=datetime(2026, 9, 25, tzinfo=timezone.utc),
            parts=[{"id": "MC-1", "name": "Rewrite the meta for clicks", "status": "done"}],
        )
    )
    db.add(
        EngineTask(
            client_id=client_a.id,
            month="2026-10",
            kind="growth_action",
            rule_id="GA",
            search="seo audit",
            page_url=page_url,
            title="Rejected GA",
            status="rejected",
            confirmed_by=admin_user.email,
            rejected_by=admin_user.email,
            rejected_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            rejection_reason="wrong_intent",
            rejection_note="Too broad for this service page",
            parts=[],
        )
    )
    db.add(
        Annotation(
            client_id=client_a.id,
            date=date(2026, 9, 26),
            annotation_type=AnnotationType.CONTENT_UPDATED,
            description="Title tag updated",
            page_url=page_url,
            verified_how="Read live on Sep 26",
            result=AnnotationResult.IMPROVED,
        )
    )
    db.commit()

    # Request with trailing slash to test URL normalization
    res = client.get(
        "/v2/engine/page-history",
        params={"page": page_url + "/"},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert res.status_code == 200
    body = res.json()
    assert body["page"] == page_url
    assert len(body["crawl_changes"]) == 1
    diff = body["crawl_changes"][0]["diff_summary"]
    assert diff["previous_count"] == 1 and diff["current_count"] == 2
    assert diff["added_count"] == 2 and diff["removed_count"] == 1

    statuses = {t["status"]: t for t in body["tasks"]}
    assert set(statuses) == {"shipped", "rejected"}
    assert statuses["rejected"]["rejection_reason"] == "wrong_intent"
    assert statuses["rejected"]["rejection_reason_label"] == "Wrong search intent"
    assert statuses["rejected"]["rejection_note"] == "Too broad for this service page"

    assert len(body["annotations"]) == 1
    assert body["annotations"][0]["result"] == "improved"
    assert body["annotations"][0]["verified_how"] == "Read live on Sep 26"

    # Client isolation: client_b gets empty history for client_a's URL
    other = client.get(
        "/v2/engine/page-history",
        params={"page": page_url},
        headers=client_header(client_b.id, admin_user.email),
    )
    assert other.status_code == 200
    assert other.json()["crawl_changes"] == [] and other.json()["tasks"] == [] and other.json()["annotations"] == []


def test_client_style_notes_crud_and_prompt_injection(client, db, tier, client_a, admin_user, team_user, monkeypatch):
    admin_h = auth_header(admin_user.email)
    created = client.post(
        "/clients",
        json={
            "client_name": "Style Co",
            "domain": "styleco.example",
            "tier_id": str(tier.id),
            "style_notes": "Keep tone warm, concise, and Australian English.",
        },
        headers=admin_h,
    )
    assert created.status_code == 201, created.text
    assert created.json()["style_notes"] == "Keep tone warm, concise, and Australian English."
    cid = created.json()["id"]

    fetched = client.get(f"/clients/{cid}", headers=admin_h)
    assert fetched.status_code == 200
    assert fetched.json()["style_notes"] == "Keep tone warm, concise, and Australian English."

    # Non-admin team_user assigned to client_a can update client_a's style_notes
    team_h = client_header(client_a.id, team_user.email)
    patched = client.patch(
        f"/clients/{client_a.id}",
        json={"style_notes": "Never use emojis or exclamation points. Cite clinical studies only."},
        headers=team_h,
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["style_notes"] == "Never use emojis or exclamation points. Cite clinical studies only."

    ctx_res = client.get("/clients/current/context", headers=team_h)
    assert ctx_res.status_code == 200
    assert ctx_res.json()["style_notes"] == "Never use emojis or exclamation points. Cite clinical studies only."

    db.refresh(client_a)
    # Injected into growth_action.build & draft, diagnose, and all 3 content_optimizer prompt kinds
    gsc(db, client_a, "mineral sunscreen", PROD, 500)
    db.commit()
    ga_out = ga.build(
        db,
        client_a,
        SEP,
        "mineral sunscreen",
        page=PROD,
        diagnose=read([sug("S-5")]),
        evidence_for=lambda s, u: {},
        signals_for=lambda s: {"reading": reading("transactional")},
    )
    assert ga_out["context"]["style_notes"] == client_a.style_notes
    draft_out = ga.draft(ga_out, "2026-10")
    assert any(client_a.style_notes in line for line in draft_out["evidence"])

    diag_out = pd.diagnose(
        search="mineral sunscreen",
        url=PROD,
        row={"position": 8.0, "impressions": 500, "clicks": 3},
        client_domain="shop.example",
        fetch=lambda u: _async_fetched(u, "<html><head><title>SPF</title></head><body><h1>SPF</h1><p>Text</p></body></html>"),
        style_notes=client_a.style_notes,
    )
    assert diag_out["context"]["style_notes"] == client_a.style_notes

    for kind in ("opening", "terms", "faq"):
        prompt = content_optimizer.build_prompt(
            kind,
            url=PROD,
            brand="Shop",
            detail={"title": "SPF", "searches": []},
            spot={"h1": "SPF", "opening": "Old opening.", "has_faq": False, "faq_questions": []},
            text="Old opening.",
            start="2026-09-01",
            end="2026-09-30",
            terms=["mineral spf"],
            style_notes=client_a.style_notes,
        )
        assert "Never use emojis or exclamation points" in prompt

    # Also verify content_optimizer.run() reads client.style_notes into LLM prompt
    today = date.today()
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=today - timedelta(days=2),
            query="mineral sunscreen",
            raw_url=PROD,
            normalized_url=PROD,
            country="usa",
            device="DESKTOP",
            impressions=200,
            clicks=2,
            ctr=0,
            average_position=9.0,
        )
    )
    db.commit()
    seen_co: list[str] = []
    monkeypatch.setattr(
        llm,
        "call",
        lambda depth, prompt, max_tokens=6000: (
            seen_co.append(prompt),
            json.dumps({"diagnosis": "Weak opening", "options": [{"text": "Better opening text here.", "serves": ["mineral sunscreen"], "why": "Direct"}]}),
            50,
            40,
        )[1:],
    )

    class _NoCloseSession:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def close(self):
            pass

    monkeypatch.setattr(content_optimizer, "SessionLocal", lambda: _NoCloseSession(db))
    run_row = content_optimizer.start(db, client_a, "opening", PROD, "quick", team_user.email, text="SPF Heading\n\nThis is a sufficiently long opening paragraph for the test.")
    content_optimizer.run(run_row.id)
    assert len(seen_co) == 1
    assert "Never use emojis or exclamation points" in seen_co[0]


async def _async_fetched(url: str, html: str) -> pd.Fetched:
    return pd.Fetched(200, url, {}, html)


# ── Area 6d: Wider DataForSEO SERPs ──────────────────────────────────────────


def test_wider_dataforseo_serps_terms_to_pull_and_serp_endpoints_and_term_detail(
    client, db, client_a, admin_user, monkeypatch
):
    client_a.client_name = "Sun Care Co"
    db.commit()
    today = date.today()

    # Seed declared target, tracked SE Ranking keyword, and watchlist keyword
    db.add(KeywordTarget(client_id=client_a.id, keyword="declared kw", target_url=PROD))
    db.add(FactSerKeyword(client_id=client_a.id, site_engine_id="se-1", keyword_id="kw-1", keyword="tracked se kw", volume=5000))
    b = WatchlistBucket(client_id=client_a.id, name="B", name_key="b", sort_order=0)
    db.add(b)
    db.flush()
    db.add(WatchlistKeyword(client_id=client_a.id, bucket_id=b.id, keyword="watched kw", keyword_key="watched kw"))

    # Seed GSC rows:
    # 1) untracked non-brand pos 12, imp 300 -> INCLUDED
    # 2) untracked non-brand pos 14, imp 150 -> INCLUDED
    # 3) brand query -> EXCLUDED
    # 4) low impressions (<25) -> EXCLUDED
    # 5) position > 20 -> EXCLUDED
    # 6) already in watchlist -> EXCLUDED from untracked tier
    gsc_rows = [
        ("untracked zinc guide", 300, 12.0),
        ("reef safe kids sunscreen", 150, 14.0),
        ("sun care co lotion", 900, 5.0),
        ("tiny query", 10, 8.0),
        ("too deep query", 400, 28.0),
        ("watched kw", 500, 11.0),
    ]
    for q, imp, pos in gsc_rows:
        db.add(
            FactGscQueryPage(
                client_id=client_a.id,
                date=today - timedelta(days=2),
                query=q,
                raw_url=PROD,
                normalized_url=PROD,
                country="usa",
                device="DESKTOP",
                impressions=imp,
                clicks=2,
                ctr=0,
                average_position=pos,
            )
        )
    db.commit()

    terms = serp_features.terms_to_pull(db, client_a, limit=12)
    assert "untracked zinc guide" in terms
    assert "reef safe kids sunscreen" in terms
    assert "declared kw" in terms
    assert "tracked se kw" in terms
    assert "sun care co lotion" not in terms
    assert "tiny query" not in terms
    assert "too deep query" not in terms

    # Verify untracked_reserve protects untracked GSC slots even when many tracked keywords exist
    for i in range(15):
        db.add(KeywordTarget(client_id=client_a.id, keyword=f"extra target {i:02d}", target_url=PROD))
    db.commit()
    reserved_terms = serp_features.terms_to_pull(db, client_a, limit=12)
    assert len(reserved_terms) == 12
    assert "untracked zinc guide" in reserved_terms

    # GET /v2/engine/serp when not yet pulled -> does NOT call dataforseo.fetch or llm.call
    fetch_calls: list[str] = []
    llm_calls: list[str] = []
    monkeypatch.setattr(dataforseo, "configured", lambda: True)
    monkeypatch.setattr(dataforseo, "keyword_overview", lambda *a, **k: [])
    monkeypatch.setattr(
        dataforseo,
        "fetch",
        lambda kw, **k: (
            fetch_calls.append(kw),
            dataforseo.SerpFeatures(
                keyword=kw,
                item_types=("organic", "people_also_ask", "ai_overview"),
                holders={"ai_overview": ("rival.example",)},
                organic=(
                    {"rank": 1, "url": "https://rival.example/zinc", "domain": "rival.example", "title": "Zinc Guide", "snippet": "..."},
                ),
                questions=("Is zinc safe for babies?",),
            ),
        )[1],
    )
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
                    "searcher_goal": "Learn whether zinc is safe for babies.",
                    "results": [{"rank": 1, "content_type": "guide or resource", "content_style": "guide"}],
                    "evidence": ["Top result is a zinc guide."],
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
    h = client_header(client_a.id, admin_user.email)

    empty_get = client.get("/v2/engine/serp", params={"search": "untracked zinc guide"}, headers=h)
    assert empty_get.status_code == 200
    assert empty_get.json()["pulled_on"] is None
    assert empty_get.json()["results"] == []
    assert fetch_calls == []
    assert llm_calls == []

    # POST /v2/engine/serp/pull calls mocked dataforseo.fetch and mocked llm.call once and stores FactSerpFeature
    pulled = client.post("/v2/engine/serp/pull", json={"search": "untracked zinc guide"}, headers=h)
    assert pulled.status_code == 200
    pdata = pulled.json()
    assert fetch_calls == ["untracked zinc guide"]
    assert llm_calls == ["quick"]
    assert pdata["item_types"] == ["organic", "people_also_ask", "ai_overview"]
    assert pdata["questions"] == ["Is zinc safe for babies?"]
    assert pdata["reading"]["intent"] == "informational"
    assert len(pdata["results"]) == 1
    assert pdata["holders"] == {"ai_overview": ["rival.example"]}

    # search_visibility.term_detail (and GET /v2/search-visibility/term) returns full serp payload
    detail = search_visibility.term_detail(db, client_a, "untracked zinc guide", today - timedelta(days=14), today)
    assert detail["serp"] is not None
    assert detail["serp"]["item_types"] == ["organic", "people_also_ask", "ai_overview"]
    assert detail["serp"]["questions"] == ["Is zinc safe for babies?"]
    assert len(detail["serp"]["results"]) == 1
    assert "reading" in detail["serp"]

    vis_res = client.get(
        "/v2/search-visibility/term",
        params={"term": "untracked zinc guide", "from": (today - timedelta(days=14)).isoformat(), "to": today.isoformat()},
        headers=h,
    )
    assert vis_res.status_code == 200
    assert vis_res.json()["serp"]["questions"] == ["Is zinc safe for babies?"]


# ── Iteration 2 Regression Tests ─────────────────────────────────────────────


def test_find_faq_page_handles_missing_faq_title_schema_self_exclusion_and_link_url_variants(db, client_a):
    target_page = f"https://{client_a.domain}/services/a"

    # 1. /faqs/ and /help-center/common-questions without FAQ keywords in <title>
    faqs_res = find_faq_page(
        db,
        client_a,
        {f"https://{client_a.domain}/faqs/": "Customer Support | Acme"},
        target_page,
        schema_urls=set(),
    )
    assert faqs_res is not None and faqs_res["id"] == "FQ-1"

    hc_res = find_faq_page(
        db,
        client_a,
        {f"https://{client_a.domain}/help-center/common-questions": "Help Center - Acme"},
        target_page,
        schema_urls=set(),
    )
    assert hc_res is not None and hc_res["id"] == "FQ-1"

    # 2. FAQPage schema on /support without FAQ slug or FAQ in <title>
    support_url = f"https://{client_a.domain}/support"
    schema_res = find_faq_page(
        db,
        client_a,
        {support_url: "Customer Support"},
        target_page,
        schema_urls={support_url},
    )
    assert schema_res is not None and schema_res["id"] == "FQ-1"

    # 3. Self-exclusion when `page` has trailing slash, www., and mixed case
    assert (
        find_faq_page(
            db,
            client_a,
            {f"https://{client_a.domain}/faqs": "FAQs"},
            f"https://WWW.{client_a.domain.upper()}/FAQS/",
            schema_urls=set(),
        )
        is None
    )

    # 4. FactCrawlInternalLink match with trailing slash / www. / mixed case suppresses FQ-1
    db.add(
        FactCrawlInternalLink(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=date(2026, 8, 25),
            from_url=f"https://www.{client_a.domain}/services/a/",
            to_url=f"https://www.{client_a.domain}/faqs/",
            in_content=True,
        )
    )
    db.commit()
    assert (
        find_faq_page(
            db,
            client_a,
            {f"https://{client_a.domain}/faqs": "Customer Support"},
            target_page,
            schema_urls=set(),
        )
        is None
    )


def test_post_ctr_title_normalizes_url_to_match_get_ctr_page(client, db, client_a, admin_user, monkeypatch):
    canonical = f"https://{client_a.domain}/products/spf-30"
    variant = f"https://WWW.{client_a.domain.upper()}/Products/SPF-30/?utm_source=email"
    today = date.today()
    start = today - timedelta(days=14)

    db.add(
        FactCrawlPageSnapshot(
            client_id=client_a.id,
            source=CRAWL_SOURCE_FIRST_PARTY,
            snapshot_date=today,
            raw_url=canonical,
            normalized_url=canonical,
            status_code=200,
            indexable=True,
            title="SPF 30",
            description="Mineral sunscreen.",
            word_count=200,
        )
    )
    db.add(
        FactGscQueryPage(
            client_id=client_a.id,
            date=today - timedelta(days=2),
            query="spf 30",
            raw_url=canonical,
            normalized_url=canonical,
            country="usa",
            device="DESKTOP",
            impressions=500,
            clicks=2,
            ctr=0,
            average_position=9.0,
        )
    )
    db.commit()

    monkeypatch.setattr(get_settings(), "anthropic_api_key", "test-key-offline")
    monkeypatch.setattr(
        llm,
        "call",
        lambda depth, prompt, max_tokens=6000: (
            json.dumps(
                {
                    "diagnosis": "Snippet needs clearer benefit.",
                    "options": [{"title": "Mineral SPF 30 Sunscreen", "serves": ["spf 30"], "why": "Direct"}],
                    "recommended": 0,
                    "descriptions": [{"description": "Lightweight zinc SPF 30 sunscreen for daily wear.", "serves": ["spf 30"], "why": "Clear"}],
                    "recommended_description": 0,
                }
            ),
            40,
            30,
        ),
    )
    monkeypatch.setattr(
        ctr_titles,
        "read_page",
        lambda u, d: pd.Fetched(200, u, {}, "<html><body><h1>SPF 30</h1><p>Daily mineral protection.</p></body></html>"),
    )

    class _NoCloseSession:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def close(self):
            pass

    monkeypatch.setattr(ctr_titles, "SessionLocal", lambda: _NoCloseSession(db))
    h = client_header(client_a.id, admin_user.email)
    res = client.post(
        "/v2/ctr/title",
        json={"url": variant, "from": start.isoformat(), "to": today.isoformat(), "depth": "quick"},
        headers=h,
    )
    assert res.status_code == 202, res.text
    draft_id = res.json()["id"]

    draft_row = db.get(CtrTitleDraft, draft_id)
    assert draft_row is not None
    assert draft_row.url == canonical

    page_res = client.get(
        "/v2/ctr/page",
        params={"url": canonical, "from": start.isoformat(), "to": today.isoformat()},
        headers=h,
    )
    assert page_res.status_code == 200
    assert page_res.json()["title_draft"] is not None
    assert page_res.json()["title_draft"]["id"] == draft_id


def test_custom_step_heading_alignment_without_space_in_subtasks_and_description(client_a):
    no_space = ["#1. Rewrite the meta for clicks", "Update title", "#2. Add trust seal", "Place near CTA"]
    with_space = ["# 1. Rewrite the meta for clicks", "Update title", "# 2. Add trust seal", "Place near CTA"]

    subs_no_space = teamwork_subtasks.from_steps(no_space, growth=True)
    subs_with_space = teamwork_subtasks.from_steps(with_space, growth=True)
    assert subs_no_space == subs_with_space
    assert [s.name for s in subs_no_space] == ["1. Rewrite the meta for clicks", "2. Add trust seal"]

    task_no_space = EngineTask(
        client_id=client_a.id,
        month="2026-10",
        kind="growth_action",
        rule_id="GA",
        search="spf 30",
        page_url=PROD,
        title="Grow SPF 30",
        steps=no_space,
        confirmed_by="admin@example.com",
    )
    task_with_space = EngineTask(
        client_id=client_a.id,
        month="2026-10",
        kind="growth_action",
        rule_id="GA",
        search="spf 30",
        page_url=PROD,
        title="Grow SPF 30",
        steps=with_space,
        confirmed_by="admin@example.com",
    )
    _, desc_no_space = v2_tasks._description(task_no_space, client_a)
    _, desc_with_space = v2_tasks._description(task_with_space, client_a)
    assert desc_no_space == desc_with_space
    assert "[ ] #1." not in desc_no_space
    assert "\n1. Rewrite the meta for clicks" in desc_no_space


def test_serp_features_terms_to_pull_limit_zero_short_circuits_without_queries(db, client_a, monkeypatch):
    called: list[str] = []
    monkeypatch.setattr(serp_features, "_page_one_queries", lambda *a, **k: called.append("p1") or ["should not run"])
    monkeypatch.setattr(serp_features, "_untracked_gsc_opportunities", lambda *a, **k: called.append("untracked") or ["should not run"])

    assert serp_features.terms_to_pull(db, client_a, limit=0) == []
    assert serp_features.terms_to_pull(db, client_a, limit=-5) == []
    assert called == []


# ── Iteration 3 Regression Tests ─────────────────────────────────────────────


def test_help_center_faq_title_discovery_and_double_hash_subheading_handling(db, client_a):
    target_page = f"https://{client_a.domain}/services/a"

    # Low #4: /help-center with FAQ title matches FQ-1 even without FAQPage schema; non-FAQ /help-center returns None
    hc_faq = find_faq_page(
        db,
        client_a,
        {f"https://{client_a.domain}/help-center": "Frequently Asked Questions | Acme"},
        target_page,
        schema_urls=set(),
    )
    assert hc_faq is not None and hc_faq["id"] == "FQ-1"

    hc_plain = find_faq_page(
        db,
        client_a,
        {f"https://{client_a.domain}/help-center": "Help Center | Acme"},
        target_page,
        schema_urls=set(),
    )
    assert hc_plain is None

    # /questions-page negative check still holds
    assert (
        find_faq_page(
            db,
            client_a,
            {f"https://{client_a.domain}/questions-page": "Common Questions"},
            target_page,
            schema_urls=set(),
        )
        is None
    )

    # Low #5: "##" subheading is NOT treated as a "#" part heading
    steps = [
        "# 1. Rewrite the meta for clicks",
        "## 1. Subheading note",
        "Update title tag",
    ]
    subs = teamwork_subtasks.from_steps(steps, growth=True)
    assert len(subs) == 1
    assert subs[0].name == "1. Rewrite the meta for clicks"
    assert "[ ] ## 1. Subheading note" in subs[0].description
    assert part_tools.from_steps(steps) == [{"id": "MC-1", "name": "Rewrite the meta for clicks"}]

    task = EngineTask(
        client_id=client_a.id,
        month="2026-10",
        kind="growth_action",
        rule_id="GA",
        search="spf 30",
        page_url=PROD,
        title="Grow SPF 30",
        steps=steps,
        confirmed_by="admin@example.com",
    )
    _, desc = v2_tasks._description(task, client_a)
    assert "\n1. Rewrite the meta for clicks\n  [ ] ## 1. Subheading note" in desc

