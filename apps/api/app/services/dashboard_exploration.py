"""Dated, source-backed dashboard drill-downs; no inferred history."""
from app.models.seranking import FactSerAiCheck, FactSerAiPrompt, FactSerKeyword
from app.services.decision_measurements import keyword_readings


def visibility_detail(db, client_id, current, previous):
    terms = {r.keyword.strip().lower(): r.keyword for r in db.query(FactSerKeyword).filter_by(client_id=client_id, is_tracked=True)}
    def readings(period):
        if not period:
            return {}
        return {term: row for term, row in keyword_readings(db, client_id, period[1]).items()
                if term in terms and row['observed_on'] >= period[0].isoformat() and row['position'] is not None}
    now, before = readings(current), readings(previous)
    matched = sorted(set(now) & set(before))
    top = lambda row: 0 < row['position'] <= 10
    rows = [{'term': label, 'current': now.get(term), 'previous': before.get(term)} for term, label in sorted(terms.items())]
    return {'tracked': len(terms), 'measured': len(now), 'top_10': sum(top(r) for r in now.values()),
            'matched': len(matched), 'matched_current_top_10': sum(top(now[t]) for t in matched),
            'matched_previous_top_10': sum(top(before[t]) for t in matched), 'keywords': rows}


def prompt_detail(db, client_id, period):
    if not period:
        return []
    engines = {r.llm_id: r.engine or r.llm_id for r in db.query(FactSerAiPrompt).filter_by(client_id=client_id)}
    latest = {}
    for row in db.query(FactSerAiCheck).filter(FactSerAiCheck.client_id == client_id,
            FactSerAiCheck.date >= period[0], FactSerAiCheck.date <= period[1]).order_by(FactSerAiCheck.date.desc()):
        latest.setdefault((row.llm_id, row.prompt_id), {'prompt': row.prompt, 'provider': engines.get(row.llm_id, row.llm_id),
            'observed_on': row.date.isoformat(), 'mentioned': row.brand_mentioned, 'cited': row.brand_cited})
    return list(latest.values())
