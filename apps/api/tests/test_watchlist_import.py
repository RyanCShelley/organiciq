"""Watchlist CSV import, against the shape of a real client account sheet.

The fixture is the Watchlist tab of the Absolutely Natural account record as
Google Sheets exports it: the topic written once per group (merged cells export
as one value and blanks), Intent / Current Position / Why merged across, so only
Intent carries text, and a notes column with no header.
"""

from __future__ import annotations

import csv
import io

import pytest

from app.models.watchlist import WatchlistBucket, WatchlistKeyword
from app.services.watchlist_import import import_watchlist, parse_watchlist_csv
from tests.conftest import client_header

HEADER = [
    "Topic", "Keyword", "Volume", "Difficulty", "Paired AI Prompt", "Intent",
    "Current Position", "Why", "",
]

MOISTURIZERS = "Face & Body Moisturizers for Dry Skin"
SUNSCREEN = "Natural & Mineral Sunscreen"
SKINCARE = "Natural & Anti-Aging Facial Skincare"
AROMA = "Aromatherapy Oils & Gift Sets"
TANNING = "Tanning Oil & After Sun Care"

ALL = "commercial/transactional/informational"

# (topic written on the first row of its group only, keyword, volume, difficulty, prompt, intent, note)
ROWS = [
    (MOISTURIZERS, "organic moisturizer", "700", "0", "what's a good organic moisturizer for dry skin in winter?", ALL, "Client-requested; KD 0"),
    ("", "face oil for dry skin", "1500", "0", "best face oil for dry skin that isn't greasy?", "commercial", "Q4 #1 priority"),
    ("", "face cream for dry skin", "1600", "0", "can you recommend a face cream for really dry skin?", ALL, "Transactional"),
    ("", "lotion for dry skin", "9100", "3", "what lotion for dry skin would you recommend for winter?", ALL, "Bestseller"),
    (SUNSCREEN, "mineral sunscreen", "43,000", "0", "which mineral sunscreen is gentle enough for my toddler?", ALL, "Core term"),
    ("", "reef safe sunscreen", "34,000", "10", "what reef safe sunscreen would you suggest for beach days?", ALL, ""),
    ("", "natural sunscreen", "10000", "24", "best natural sunscreen for sensitive skin that doesn't leave white cast?", ALL, ""),
    ("", "is sunscreen fsa eligible", "1100", "0", "which sunscreens are fsa eligible you'd actually recommend?", "commercial/informational", ""),
    (SKINCARE, "natural skincare", "3800", "25", "can you recommend a natural skincare routine that's simple and affordable?", ALL, ""),
    ("", "anti aging skincare", "2200", "24", "which anti aging skincare is worth it without a complicated routine?", "commercial/informational", ""),
    ("", "organic skin care products", "1100", "0", "what organic skin care products do you trust for simple routines?", ALL + "/local", ""),
    ("", "facial serum", "2900", "30", "which facial serum would you pick for dull, tired looking skin?", ALL, ""),
    (AROMA, "aromatherapy gift set", "250", "0", "what aromatherapy gift set would you pick for my mom's birthday?", "commercial/transactional", ""),
    ("", "aromatherapy oils", "600", "31", "which aromatherapy oils are good for beginners who want calming scents?", ALL + "/local", ""),
    ("", "aromatherapy products", "1100", "32", "any aromatherapy products you'd recommend for winter evenings at home?", ALL, ""),
    ("", "essential oil set", "450", "0", "what essential oil set would you recommend for a first-time buyer?", "commercial/transactional", ""),
    (TANNING, "tanning oil", "10000", "2", "what tanning oil would you recommend that won't leave me greasy?", ALL, "Ranks #6"),
    ("", "after sun lotion", "9100", "0", "best after sun lotion for my sunburned shoulders this weekend?", ALL, ""),
]


def sheet_csv(rows=ROWS, header=HEADER, leading: list[list[str]] | None = None) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    for extra in leading or []:
        writer.writerow(extra)
    writer.writerow(header)
    for topic, keyword, volume, difficulty, prompt, intent, note in rows:
        # Current Position and Why are merged into Intent, so they export blank.
        writer.writerow([topic, keyword, volume, difficulty, prompt, intent, "", "", note])
    return out.getvalue()


def test_the_real_sheet_parses_to_five_buckets_and_eighteen_keywords():
    parsed = parse_watchlist_csv(sheet_csv())

    assert len(parsed.rows) == 18
    assert [r.topic for r in parsed.rows if not r.topic_inherited] == [
        MOISTURIZERS, SUNSCREEN, SKINCARE, AROMA, TANNING,
    ]
    assert sum(r.topic_inherited for r in parsed.rows) == 13
    assert {r.topic for r in parsed.rows} == {MOISTURIZERS, SUNSCREEN, SKINCARE, AROMA, TANNING}
    assert parsed.skipped == [] and parsed.warnings == []


def test_columns_left_out_are_reported_not_silently_dropped():
    parsed = parse_watchlist_csv(sheet_csv())
    assert "Current Position" in parsed.ignored_columns
    assert "Why" in parsed.ignored_columns
    assert "(unlabelled column 9)" in parsed.ignored_columns


def test_volumes_with_thousands_separators_parse():
    parsed = parse_watchlist_csv(sheet_csv())
    by_keyword = {r.keyword: r for r in parsed.rows}
    assert by_keyword["mineral sunscreen"].values["volume"] == 43000
    assert by_keyword["tanning oil"].values["difficulty"] == 2


def test_import_stores_prompts_and_intent(db, client_a):
    report = import_watchlist(db, client_a, sheet_csv())

    assert report["buckets_created"] == 5
    assert report["keywords_created"] == 18
    assert report["topics_inherited"] == 13

    row = db.query(WatchlistKeyword).filter_by(keyword="face oil for dry skin").one()
    assert row.paired_ai_prompt == "best face oil for dry skin that isn't greasy?"
    assert row.intent == "commercial"
    assert row.volume == 1500
    assert row.bucket_id == db.query(WatchlistBucket).filter_by(name=MOISTURIZERS).one().id

    face_cream = db.query(WatchlistKeyword).filter_by(keyword="face cream for dry skin").one()
    assert "dull" not in (face_cream.paired_ai_prompt or "")
    serum = db.query(WatchlistKeyword).filter_by(keyword="facial serum").one()
    assert serum.paired_ai_prompt == "which facial serum would you pick for dull, tired looking skin?"


def test_importing_twice_changes_nothing(db, client_a):
    import_watchlist(db, client_a, sheet_csv())
    again = import_watchlist(db, client_a, sheet_csv())

    assert again["keywords_created"] == 0
    assert again["buckets_created"] == 0
    assert again["keywords_updated"] == 0
    assert again["keywords_unchanged"] == 18
    assert db.query(WatchlistKeyword).count() == 18


def test_dry_run_reports_and_writes_nothing(db, client_a):
    report = import_watchlist(db, client_a, sheet_csv(), dry_run=True)

    assert report["dry_run"] is True
    assert report["keywords_created"] == 18 and report["buckets_created"] == 5
    assert db.query(WatchlistKeyword).count() == 0
    assert db.query(WatchlistBucket).count() == 0


def test_a_changed_cell_updates_and_a_blank_cell_never_erases(db, client_a):
    import_watchlist(db, client_a, sheet_csv())

    edited = [list(r) for r in ROWS]
    edited[4][2] = "50,000"  # mineral sunscreen volume
    edited[1][4] = ""  # face oil prompt cleared in the sheet
    report = import_watchlist(db, client_a, sheet_csv([tuple(r) for r in edited]))

    assert report["keywords_updated"] == 1
    assert db.query(WatchlistKeyword).filter_by(keyword="mineral sunscreen").one().volume == 50000
    kept = db.query(WatchlistKeyword).filter_by(keyword="face oil for dry skin").one()
    assert kept.paired_ai_prompt == "best face oil for dry skin that isn't greasy?"


def test_a_keyword_moved_to_another_topic_changes_bucket(db, client_a):
    import_watchlist(db, client_a, sheet_csv())

    moved = [list(r) for r in ROWS]
    moved[17] = [AROMA] + moved[17][1:]  # after sun lotion, now written under Aromatherapy
    report = import_watchlist(db, client_a, sheet_csv([tuple(r) for r in moved]))

    assert report["keywords_updated"] == 1
    row = db.query(WatchlistKeyword).filter_by(keyword="after sun lotion").one()
    assert row.bucket_id == db.query(WatchlistBucket).filter_by(name=AROMA).one().id


def test_a_column_the_file_lacks_is_left_alone(db, client_a):
    import_watchlist(db, client_a, sheet_csv())
    only_volumes = "Topic,Keyword,Volume\nNatural & Mineral Sunscreen,mineral sunscreen,1\n"
    import_watchlist(db, client_a, only_volumes)

    row = db.query(WatchlistKeyword).filter_by(keyword="mineral sunscreen").one()
    assert row.volume == 1
    assert row.paired_ai_prompt == "which mineral sunscreen is gentle enough for my toddler?"
    assert row.intent == ALL


def test_a_header_below_a_title_row_is_found():
    parsed = parse_watchlist_csv(sheet_csv(leading=[["Absolutely Natural watchlist"], []]))
    assert len(parsed.rows) == 18


def test_no_header_is_an_error():
    with pytest.raises(ValueError, match="header row"):
        parse_watchlist_csv("Name,Value\nfoo,1\n")


def test_rows_that_cannot_be_used_are_skipped_with_a_reason():
    text = "Topic,Keyword\n,orphan keyword\nSEO,\nSEO,real keyword\n"
    parsed = parse_watchlist_csv(text)

    assert [r.keyword for r in parsed.rows] == ["real keyword"]
    reasons = {s["line"]: s["reason"] for s in parsed.skipped}
    assert "no topic" in reasons[2]
    assert reasons[3] == "no keyword"


def test_a_bad_number_is_a_warning_and_the_row_still_imports():
    parsed = parse_watchlist_csv("Topic,Keyword,Volume,Difficulty\nSEO,term,lots,150\n")

    assert len(parsed.rows) == 1
    assert "volume" not in parsed.rows[0].values and "difficulty" not in parsed.rows[0].values
    assert len(parsed.warnings) == 2


def test_a_repeated_keyword_uses_the_later_row():
    parsed = parse_watchlist_csv("Topic,Keyword,Volume\nSEO,term,1\nSEO,Term ,2\n")

    assert len(parsed.rows) == 1 and parsed.rows[0].values["volume"] == 2
    assert "also on line 2" in parsed.warnings[0]["reason"]


def test_api_import_then_read(client, db, client_a, admin_user):
    headers = client_header(client_a.id, admin_user.email)

    preview = client.post(
        "/v2/watchlist/import", json={"csv_text": sheet_csv(), "dry_run": True}, headers=headers
    )
    assert preview.status_code == 200 and preview.json()["keywords_created"] == 18
    assert client.get("/v2/watchlist", headers=headers).json()["keyword_count"] == 0

    done = client.post("/v2/watchlist/import", json={"csv_text": sheet_csv()}, headers=headers)
    assert done.status_code == 200 and done.json()["buckets_created"] == 5

    body = client.get("/v2/watchlist", headers=headers).json()
    assert body["keyword_count"] == 18
    assert [b["name"] for b in body["buckets"]] == [MOISTURIZERS, SUNSCREEN, SKINCARE, AROMA, TANNING]
    sunscreen = body["buckets"][1]["keywords"]
    assert sunscreen[0]["keyword"] == "mineral sunscreen" and sunscreen[0]["volume"] == 43000


def test_api_rejects_a_file_without_a_header(client, db, client_a, admin_user):
    response = client.post(
        "/v2/watchlist/import",
        json={"csv_text": "Name,Value\nfoo,1\n"},
        headers=client_header(client_a.id, admin_user.email),
    )
    assert response.status_code == 400
    assert "header row" in response.json()["detail"]


def test_api_import_needs_a_client(client, db, client_a, admin_user):
    from tests.conftest import auth_header

    response = client.post(
        "/v2/watchlist/import", json={"csv_text": sheet_csv()}, headers=auth_header(admin_user.email)
    )
    assert response.status_code == 400
