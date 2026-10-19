"""Read-only leads for human investigation, never automatic findings or tasks."""
from datetime import date
from hashlib import sha256
import math


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def _dated(value):
    try:
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def review_opportunities(data):
    """Explain material observations without inferring a site defect or remedy.

    These are screening criteria, not significance tests: traffic needs >=100
    previous visits, >=50 lost visits and >=20% decline; rankings need dated
    matched readings, a previous top-20 position and >=10 positions lost;
    limited reach needs >=5 measured terms and >=50% outside the top 100.
    No inputs, approvals, work identities or saved assessments are mutated.
    """
    measurements = data.get('measurements') or {}
    visibility = measurements.get('visibility') or {}
    out = []

    def add(kind, title, summary, evidence, checks, target_url='', term=None):
        out.append({
            'uid': 'review-' + sha256(f"{data.get('month')}:{kind}".encode()).hexdigest()[:20],
            'kind': kind, 'title': title, 'summary': summary, 'evidence': evidence,
            'review_checks': checks, 'target_url': target_url, 'term': term,
            'assessment_month': data.get('month'),
            'screening_rule': {
                'traffic_decline': 'At least 100 previous visits, 50 lost visits and a 20% decline across matching periods.',
                'ranking_loss': 'Dated readings for a current tracked term: previously in the top 20, then at least 10 positions lost.',
                'limited_reach': 'At least five dated, measured target terms, with at least half outside the top 100.',
            }[kind],
            'limitation': 'This observation is not a verified page defect or an execution-ready fix.',
        })

    traffic = measurements.get('traffic') or {}
    current, previous = traffic.get('current') or {}, traffic.get('previous') or {}
    now, before = _number(current.get('total')), _number(previous.get('total'))
    start, end = _dated(measurements.get('start')), _dated(measurements.get('end'))
    prior_start, prior_end = _dated(measurements.get('prior_start')), _dated(measurements.get('prior_end'))
    comparable_periods = (all((start, end, prior_start, prior_end))
                          and (end-start).days == (prior_end-prior_start).days
                          and (end-start).days >= 6 and prior_end < start)
    if comparable_periods and now is not None and before is not None and now >= 0 and before >= 100 and before-now >= 50 and now/before <= .8:
        drivers = []
        prior_channels = previous.get('channels') or {}
        for channel, value in (current.get('channels') or {}).items():
            a, b = _number(value), _number(prior_channels.get(channel))
            if a is not None and b is not None and 0 <= a < b:
                label = {'direct_unattributed': 'Direct / Unattributed', 'ai_referral': 'AI Referral'}.get(channel, channel.replace('_', ' ').title())
                drivers.append((b-a, f"{label}: {b:,.0f} → {a:,.0f} detailed visits."))
        drivers.sort(reverse=True)
        add('traffic_decline', 'Review the decline in site visits',
            f"Visits fell {(before-now)/before*100:.1f}% ({before-now:,.0f} visits) against the assessment's matched previous period.",
            [f"Whole-site visits: {before:,.0f} → {now:,.0f}.", f"Periods: {prior_start} – {prior_end} compared with {start} – {end}.", *[row[1] for row in drivers[:2]]],
            ['Check channel and landing-page changes, tracking continuity and client activity before choosing work.',
             'Direct traffic remains unattributed; the change alone does not prove SEO impact or a page defect.'])

    keywords = visibility.get('keywords') or []
    by_term = {str(row.get('text', '')).strip().lower(): row for row in keywords if str(row.get('text') or '').strip()}
    losses = []
    seen_losses = set()
    for row in (visibility.get('monthly_trend') or {}).get('rows') or []:
        now, before = _number(row.get('current')), _number(row.get('previous'))
        current_date, previous_date = _dated(row.get('current_date')), _dated(row.get('previous_date'))
        if (now is None or before is None or not current_date or not previous_date or current_date <= previous_date or current_date.isoformat()[:7] != data.get('month')
                or not 1 <= before <= 20 or not 1 <= now <= 101 or now-before < 10):
            continue
        term = str(row.get('text') or '').strip()
        if term.lower() not in by_term or term.lower() in seen_losses:
            continue  # Do not expand current tracked focus with historical terms.
        seen_losses.add(term.lower())
        losses.append((now-before, term, row))
    if losses:
        losses.sort(key=lambda row: (-row[0], row[1]))
        _, term, strongest = losses[0]
        evidence = []
        for _, text, row in losses[:3]:
            position = 'outside the top 100' if row['current'] > 100 else f"position {row['current']:g}"
            evidence.append(f"{text}: position {row['previous']:g} ({row['previous_date']}) → {position} ({row['current_date']}).")
        add('ranking_loss', 'Review losses among previously strong keywords',
            f"{len(losses)} current tracked {'term lost' if len(losses)==1 else 'terms lost'} at least 10 positions after previously ranking in the top 20.",
            evidence, ['Compare the observed ranking URL, intended page and search intent; check migration or indexing changes.',
                       'Confirm the cause before choosing content, linking or technical work. Exact wording alone is not a defect.'],
            target_url=by_term[term.lower()].get('target_url') or '', term=term)

    # Require a dated, explicit measured status; missing rankings are not failures.
    measured_statuses = {'top_10', 'top_100', 'not_in_top_100'}
    measured = [row for row in by_term.values() if row.get('status') in measured_statuses and _dated(row.get('observed_on')) and row['observed_on'][:7] == data.get('month')]
    outside = [row for row in measured if row.get('status') == 'not_in_top_100']
    if len(measured) >= 5 and len(outside)/len(measured) >= .5:
        add('limited_reach', 'Review limited reach across target keywords',
            f"{len(outside)} of {len(measured)} measured target terms are outside the top 100.",
            [f"Current dated readings cover {len(measured)} tracked terms; unmeasured terms are excluded.",
             'Examples: ' + '; '.join(str(row.get('text')) for row in outside[:5]) + '.'],
            ['Review keyword intent, page ownership and current competing results to choose the right opportunity.',
             'These current readings do not establish a decline, a content gap or a required new page.'])
    return out[:3]
