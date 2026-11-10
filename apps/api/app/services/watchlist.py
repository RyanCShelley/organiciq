from hashlib import sha256

from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword
from app.models.watch_target import WatchTarget


def item_key(kind, text, provider=""):
    return sha256(f"{kind}:{provider or ''}:{text.strip().lower()}".encode()).hexdigest()


def read(db, client):
    rows = {}
    maps = {x.keyword: x for x in db.query(KeywordTarget).filter(KeywordTarget.client_id == client.id)}
    keywords = {x.keyword for x in db.query(FactSerKeyword).filter(FactSerKeyword.client_id == client.id)} | set(maps)
    for text in sorted(keywords):
        if not text:
            continue
        mapped = maps.get(text)
        key = item_key("keyword", text)
        rows[("keyword", key)] = dict(kind="keyword", item_key=key, text=text, provider=None,
            state="existing" if mapped and mapped.target_url and mapped.source in ("confirmed", "auto") else "unmapped",
            target_url=mapped.target_url if mapped and mapped.source in ("confirmed", "auto") else None, priority=bool(mapped and mapped.priority),
            note=mapped.note if mapped else None, observation={})
    from datetime import date

    from app.llm_visibility import readings as llm_readings

    # The prompts are the LLM tracker's own: each platform's newest answer to each prompt it asks.
    for (platform, _), seen in sorted(llm_readings.prompt_readings(db, client.id, date.today()).items()):
        if seen["asked_by_name"]:
            continue  # a prompt that names the brand is a brand check, not a discovery prompt to act on
        key = item_key("prompt", seen["prompt"], platform)
        rows[("prompt", key)] = dict(kind="prompt", item_key=key, text=seen["prompt"], provider=platform,
            state="unmapped", target_url=None, priority=False, note=None,
            observation={"observed_on": seen["observed_on"], "brand_mentioned": seen["brand_mentioned"],
                         "brand_cited": seen["brand_cited"], "source": llm_readings.SOURCE})
    for target in db.query(WatchTarget).filter(WatchTarget.client_id == client.id):
        previous = rows.get((target.kind, target.item_key), {})
        rows[(target.kind, target.item_key)] = {field: getattr(target, field) for field in (
            "kind", "item_key", "text", "provider", "state", "target_url", "priority", "note")}
        rows[(target.kind, target.item_key)]["observation"] = target.observation or previous.get("observation", {})
    return sorted(rows.values(), key=lambda x: (x["kind"], not x["priority"], x["text"]))


def write(db, client, payload):
    key = item_key(payload.kind, payload.text, payload.provider)
    row = db.query(WatchTarget).filter(WatchTarget.client_id == client.id,
        WatchTarget.kind == payload.kind, WatchTarget.item_key == key).one_or_none()
    if row is None:
        row = WatchTarget(client_id=client.id, kind=payload.kind, item_key=key)
        db.add(row)
    for field in ("text", "provider", "state", "target_url", "priority", "note", "observation"):
        setattr(row, field, getattr(payload, field))
    if payload.kind == "keyword":
        term = payload.text.strip().lower()
        mapped = db.query(KeywordTarget).filter(KeywordTarget.client_id == client.id, KeywordTarget.keyword == term).one_or_none()
        if mapped is None:
            mapped = KeywordTarget(client_id=client.id, keyword=term, source="confirmed")
            db.add(mapped)
        mapped.source = "confirmed"
        mapped.confidence = None
        mapped.target_url = payload.target_url if payload.state == "existing" else None
        mapped.priority = payload.priority and payload.state != "excluded"
        mapped.note = payload.note
    db.commit()
    return read(db, client)


def automatic_focus(db, client):
    """Current tracker terms plus prompt targets; maps remain ownership evidence."""
    terms = {(row.keyword or "").strip().lower() for row in
             db.query(FactSerKeyword).filter_by(client_id=client.id, is_tracked=True)}
    return [row for row in read(db, client)
            if row["kind"] != "keyword" or row["text"].strip().lower() in terms]
