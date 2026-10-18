from hashlib import sha256

from app.models.decision import KeywordTarget
from app.models.seranking import FactSerKeyword, FactSerAiPrompt
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
    for prompt in db.query(FactSerAiPrompt).filter(FactSerAiPrompt.client_id == client.id):
        provider = prompt.engine or prompt.llm_id
        key = item_key("prompt", prompt.prompt, provider)
        rows[("prompt", key)] = dict(kind="prompt", item_key=key, text=prompt.prompt, provider=provider,
            state="unmapped", target_url=None, priority=False, note=None,
            observation={k: v for k, v in {"observed_on": str(prompt.checked_at) if prompt.checked_at else None,
                         "brand_mentioned": prompt.brand_mentioned, "brand_cited": prompt.brand_cited,
                         "citation_url": prompt.citation_url, "source": "SE Ranking"}.items() if v is not None})
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
