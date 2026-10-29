"""Connect proposed interventions to their own saved page findings.

A shared page, branch or monthly trend is context, never proof of causation.
No source calls, new prescriptions, approvals or mutations happen here.
"""
from copy import deepcopy
from app.decisions.planning import page_identity

# Page-wide checks can be reported against more than one tracked term.
PAGE_CHECKS = {'T-1', 'T-3', 'V-7', 'V-4', 'L-1', 'L-2', 'L-3'}
RATIONALE = {
    'V-7': 'The crawl found a visible FAQ section without matching FAQPage markup. Matching the markup to the visible answers addresses that specific gap; it does not explain a ranking loss.',
    'T-1': 'Recorded clicks are below a CTR reference scenario at this position. Review the query intent and actual search result before changing the title or description; the benchmark does not establish a snippet defect.',
    'T-3': 'Measured engagement is below the site comparison. Review this page’s visitor intent before deciding on an opening rewrite; low engagement alone does not prove a content defect.',
    'V-4': 'This page has low editorial support and named, relevant donor pages without an observed body link. The proposed links address the verified linking gap.',
    'L-1': 'The measured page lacks an observed in-content route to a configured, stage-matched offer. The recommended route addresses that specific path gap.',
    'L-2': 'The eligible page has no observed conversion element. A stage-appropriate call to action addresses the measured gap.',
    'L-3': 'The observed offer routes do not fit the confirmed reader stage and a matching offer exists. The task changes the destination to that matched offer.',
}


def explain(item, assessment):
    """Match rule AND page, plus term for term-specific checks."""
    page = item.get('target_url') or ''
    rule_ids = set(item.get('finding_ids') or [item.get('id')])
    term = (item.get('term') or '').strip().casefold()
    matches = []
    for found in assessment.get('findings', assessment.get('candidates') or assessment.get('actions') or []):
        rule = found.get('id')
        if rule not in rule_ids or not page or not found.get('target_url'):
            continue
        # Individual growth actions retain the rule and prescription that
        # produced them. A custom rewrite cannot inherit an automated claim.
        if len(item.get('steps') or []) == 1 and item.get('id') != rule:
            continue
        if len(item.get('steps') or []) == 1 and found.get('steps') and item['steps'][0] not in found['steps']:
            continue
        if page_identity(page) != page_identity(found['target_url']):
            continue
        if rule not in PAGE_CHECKS and term != (found.get('term') or '').strip().casefold():
            continue
        matches.append({
            'uid': found.get('action_uid'), 'rule_id': rule,
            'page': found['target_url'], 'term': found.get('term'),
            'observation': found.get('why') or '', 'evidence': list(found.get('evidence') or []),
        })
    return {
        'status': 'supported' if matches else 'unresolved',
        'findings': matches,
        'why_this_action': RATIONALE.get(item.get('id'), item.get('why') or '') if matches else 'No matching page finding supports this task in the saved assessment.',
        'outcome': item.get('metric') or 'Manual verification',
        'limitation': ('This action addresses the linked finding. It is not established as the cause of an unrelated ranking, traffic or lead change.' if matches else 'This is not an automatically verified prescription; its scope needs an explicit human decision.'),
    }


def connect(proposals, assessment):
    """Return enriched copies; never rewrite saved decisions or task identities."""
    out = deepcopy(proposals)
    for item in out:
        item['reasoning'] = explain(item, assessment)
        for task in item.get('interventions') or []:
            task['reasoning'] = explain(task, assessment)
    return out
