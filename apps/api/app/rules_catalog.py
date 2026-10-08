"""Every check the engine runs, and how each one is scored.

Growth actions are a limited budget, separate from core work, so the list
of things competing for them has to be reviewable in one place — and has
to be true. Written by hand it would drift from the code within a week, so
the machine-readable half is read out of the code itself: which lever a
rule files under, whether it is core work or competes for an action,
whether it can preempt, and the confidence, urgency and effort it carries.

The prose half — what each rule actually checks — is maintained here
beside the signal it belongs to, and `--audit` lists any signal the code
emits that this file has not described.

    python -m app.rules_catalog            # markdown to stdout
    python -m app.rules_catalog --audit    # anything undocumented
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from app.decisions.prescription import CAUSES
from app.decisions.thresholds import DEFAULT_DECISION_THRESHOLDS as LIMITS
from app.decisions.actions.value import DEFAULT_MINUTES
from app.services.lever_engine import (
    ACTION_RULE_IDS,
    INDEXATION_BLOCKING_SIGNALS,
    LEVER_LABELS,
    ROBOTS_ADVISORY_CODES,
    SIGNAL_LEVERS,
    TECHNICAL_ACTIONS,
    is_core_work_signal,
)

#: Both files that can name a check: the engine, and the crawler, which
#: raises the site-level ones it finds while planning the crawl.
SOURCES = (
    Path(__file__).resolve().parent / "services" / "lever_engine.py",
    Path(__file__).resolve().parent / "ingestion" / "crawler" / "pipeline.py",
)


def _t(key: str) -> str:
    value = LIMITS.get(key)
    return f"`{key}` ({value})"


#: What each rule checks, in the order the engine asks. Keyed by the signal
#: or gate the finding carries, which is what the UI and the API show.
CHECKS: dict[str, dict[str, str]] = {
    # ── Leads ──
    "tracking": {
        "question": "Are conversions being recorded at all?",
        "fires": (
            "No conversions in 14 days while sessions still arrive, and the "
            "fortnight should have produced at least 3 leads (or, with no history, "
            "500 sessions arrived)."
        ),
        "impact": "Leads the fortnight should have produced, as leads at risk.",
        "notes": "The only check that suppresses others: every score below it is computed from a lead count it says is wrong.",
    },
    "tracking_partial": {
        "question": "Has one page stopped converting while the rest of the site has not?",
        "fires": (
            f"A page produces nothing for {_t('partial_break_days')} days while the site "
            f"still converts, and its own prior rate applied to the traffic it still "
            f"gets expects at least {_t('partial_break_min_expected_leads')} leads."
        ),
        "impact": "Expected leads from that page, as leads at risk.",
        "notes": "Suppresses nothing. A page with no visitors is skipped: no leads is arithmetic, not a fault.",
    },
    "tracking_spike": {
        "question": "Are leads far above the usual rate?",
        "fires": (
            f"Leads past {_t('lead_spike_multiple')}x the rate the same traffic used to "
            f"produce, with at least {_t('lead_spike_min_leads')} recorded."
        ),
        "impact": "The excess over the expected rate — the recorded leads that may not exist.",
        "notes": "What double firing and form spam look like.",
    },
    "site_conversion": {
        "question": "Is the site converting at the level the plan requires?",
        "fires": (
            f"The lead rate fell {_t('conversion_lead_rate_decline_min_pct')}%, or sessions "
            f"grew {_t('conversion_sessions_growth_min_pct')}% without leads following, or "
            f"the rate sits below the client's own starting baseline. Each trigger needs "
            f"{_t('gate1_min_expected_leads')} expected leads behind it."
        ),
        "impact": "Leads lost against the previous period, or the gap to plan.",
        "notes": "Routes to one page when 60% of the loss sits there; says 'hold the plan' when last year fell the same way.",
    },
    "conversion_page": {
        "question": "Does a page earn traffic and convert below its own page type?",
        "fires": (
            f"The page type has at least {_t('gate3_page_type_min_pages')} pages and "
            f"{_t('gate3_page_type_min_leads')} leads behind it to compare against."
        ),
        "impact": "Leads the page would produce at its page type's rate.",
        "notes": "",
    },
    "no_conversion_element": {
        "question": "Is there anything on the page to convert through?",
        "fires": (
            f"No form, phone link, email link or call-to-action button on a page with "
            f"{_t('cta_min_sessions')} sessions. Only counted from a page that returned 2xx."
        ),
        "impact": "Scored on the page's own traffic.",
        "notes": "A null count means the crawl predates the check, which is not the same as zero.",
    },
    # ── Traffic ──
    "serp_ctr": {
        "question": "Is the listing earning the clicks the position should?",
        "fires": (
            f"Position 1 to {_t('serp_ctr_max_position')}, at least 1,000 impressions, CTR "
            "under half the measured curve, and at least 5 clicks recoverable. Pages where "
            "brand is over half the impressions are skipped."
        ),
        "impact": "Recoverable clicks converted at the site's lead rate.",
        "notes": "Stops at five on purpose: the curve pays 0.73% at six, so there is no click to win back by rewriting a listing.",
    },
    "rank_push": {
        "question": "Does a page sit just below where the clicks are?",
        "fires": (
            f"Position above {_t('serp_ctr_max_position')} and up to "
            f"{_t('rank_push_max_position')}, with at least "
            f"{_t('rank_push_min_impressions')} impressions and 5 clicks to gain at "
            "position five."
        ),
        "impact": "Clicks gained reaching position five, converted at the site's lead rate.",
        "notes": "The band CTR work cannot reach. The instruction is rank, not the listing.",
    },
    # ── Visibility ──
    "internal_linking": {
        "question": "Do enough pages link to it?",
        "fires": (
            f"Editorial inbound links below the floor for what the page is for — "
            f"{_t('link_floor_money')} for money pages, {_t('link_floor_industry')} for "
            f"industry pages, {_t('link_floor_blog')} for posts — at position 4 to 20."
        ),
        "impact": "Clicks a better position would earn, converted at the site's lead rate.",
        "notes": f"The homepage is never reported. Donors capped at {_t('link_max_donors')}.",
    },
    "keyword_not_ranking": {
        "question": "Is a tracked term outside the top 100?",
        "fires": (
            f"Volume at least {_t('ai_visibility_min_keyword_volume')}; the top "
            f"{_t('ai_visibility_keyword_top_n')} by volume are reported."
        ),
        "impact": (
            f"Volume x the curve at {_t('keyword_target_position')} x a difficulty discount "
            f"(floored at {_t('keyword_difficulty_floor')}) x the site's lead rate, capped at "
            f"{_t('single_opportunity_max_lead_share')} of the period goal."
        ),
        "notes": "Reads the keyword-to-page map first; without one it asks for the mapping rather than guessing.",
    },
    "keyword_fell_top5": {
        "question": "Did a term fall out of the top five?",
        "fires": "Previous position 5 or better, now worse than 5.",
        "impact": "18% of volume as recoverable clicks, converted at the site's lead rate.",
        "notes": "A term that was ranking has shown it can rank, so the share is a property of the fall rather than the curve.",
    },
    "keyword_fell_top10": {
        "question": "Did a term fall out of the top ten?",
        "fires": "Previous position 10 or better, now worse than 10.",
        "impact": "10% of volume as recoverable clicks, converted at the site's lead rate.",
        "notes": "",
    },
    "prompt_not_cited": {
        "question": "Do answer engines cite the brand for a tracked prompt?",
        "fires": (
            f"At least {_t('ai_visibility_prompt_min_checks')} checks in the period with no "
            f"citation; the top {_t('ai_visibility_prompt_top_n')} are reported."
        ),
        "impact": "12% of prompt volume as recoverable clicks, converted at the site's lead rate.",
        "notes": "A blocked AI crawler preempts everything else: an engine that cannot fetch the page will never cite it.",
    },
    # ── Technical ──
    "status_error": {
        "question": "Does the page return 4xx or 5xx?",
        "fires": "On a page with demand, or in the sitemap, or commercial/conversion.",
        "impact": "Addressable clicks behind the error, converted at the site's lead rate.",
        "notes": "",
    },
    "soft_404": {
        "question": "Does the page return 200 while saying it is missing?",
        "fires": "A 2xx whose title or H1 is about being not found.",
        "impact": "As above.",
        "notes": "Google drops these exactly as it drops a real 404. SE Ranking has no such check; the first-party crawler does it.",
    },
    "non_indexable": {
        "question": "Is the page excluded from the index?",
        "fires": "noindex, on a page with demand. A working redirect is not reported.",
        "impact": "As above.",
        "notes": "",
    },
    "canonical_elsewhere": {
        "question": "Does the canonical point somewhere unusable?",
        "fires": "The target is off-site, missing from the crawl, erroring, or itself non-indexable.",
        "impact": "As above.",
        "notes": "A canonical pointing at a live page on the same site is correct consolidation and is not reported.",
    },
    "orphan_page": {
        "question": "Does anything link to the page?",
        "fires": f"No inbound internal links, with at least {_t('orphan_min_impressions')} impressions.",
        "impact": "As above.",
        "notes": "Demand is the qualifier: most orphans are drafts and thank-you pages.",
    },
    "blocked_resources": {
        "question": "Can Google render the page?",
        "fires": "Scripts or stylesheets the page loads that robots.txt disallows, on the same host.",
        "impact": "As above.",
        "notes": "A CDN has its own rules we have not read, so its resources are not counted.",
    },
    "broken_redirect": {
        "question": "Does a redirect land on an error?",
        "fires": "A 3xx whose target returns 4xx or 5xx.",
        "impact": "As above.",
        "notes": "",
    },
    "redirect_chain": {
        "question": "How many hops before the page?",
        "fires": "Three or more.",
        "impact": "As above.",
        "notes": "",
    },
    "title_missing": {
        "question": "Does the page have a title?",
        "fires": "Empty title on a page with demand.",
        "impact": "As above.",
        "notes": "Files under SERP & CTR, not Technical: a title earns the click, so it competes for an action.",
    },
    "title_duplicate": {
        "question": "Does the title belong to another page too?",
        "fires": "Duplicate title on a page with demand.",
        "impact": "As above.",
        "notes": "Also SERP & CTR.",
    },
    "description_missing": {
        "question": "Does the page have a meta description?",
        "fires": "Empty description on a page with demand.",
        "impact": "As above.",
        "notes": "Core work. Google rewrites descriptions at will.",
    },
    "description_duplicate": {
        "question": "Does the description belong to another page too?",
        "fires": "Duplicate description on a page with demand.",
        "impact": "As above.",
        "notes": "Core work.",
    },
    "missing_schema": {
        "question": "Does the page carry structured data that says what it is?",
        "fires": "No markup, or only the site-wide boilerplate a plugin emits everywhere.",
        "impact": "As above.",
        "notes": "Core work. Only on pages the first-party crawl actually reached.",
    },
    "invalid_schema": {
        "question": "Does the structured data parse?",
        "fires": "Markup present and unreadable.",
        "impact": "As above.",
        "notes": "Core work.",
    },
    "sitemap_missing": {
        "question": "Is there an XML sitemap?",
        "fires": "None declared and none at the usual locations, on any host.",
        "impact": "Site-level; scored on the site's own figures.",
        "notes": "Core work.",
    },
    "robots_disallow_crawling": {
        "question": "Does robots.txt disallow crawling?",
        "fires": "robots.txt tells our agent not to crawl the site at all.",
        "impact": "Site-level; reaches the engine as the blocking signal `robots_blocking`.",
        "notes": "Blocking: it stops everything else being measurable.",
    },
    "no_robots": {
        "question": "Is there a robots.txt?",
        "fires": "Nothing served at /robots.txt, or what is served is not a robots file.",
        "impact": "Site-level.",
        "notes": "Core work. Advisory — a missing robots.txt means crawl freely.",
    },
    "robots_not_accessible": {
        "question": "Can robots.txt be fetched?",
        "fires": "The request for it failed, as opposed to returning nothing.",
        "impact": "Site-level.",
        "notes": "Core work. Different from absent: something is there and unreachable.",
    },
    "robots_has_errors": {
        "question": "Is the declared sitemap readable?",
        "fires": "robots.txt declares a sitemap and it yields nothing.",
        "impact": "Site-level.",
        "notes": "Core work. Declared and broken is worse than absent: something references it.",
    },
    "ai_crawlers_blocked": {
        "question": "Can answer engines fetch the site?",
        "fires": "robots.txt disallows GPTBot, OAI-SearchBot, PerplexityBot, ClaudeBot, Google-Extended or similar.",
        "impact": "Reported through the prompt rule rather than scored on its own.",
        "notes": "Usually a plugin's default rule rather than a decision anyone made.",
    },
    "ai_readiness": {
        "question": "Does the structured data say who the brand is, consistently?",
        "fires": (
            "Any of three checks fail across the Organization, LocalBusiness or "
            "ProfessionalService blocks in the latest crawl: the site gives itself "
            "more than one name; a `url` property points at a host that is not the "
            "client's; or the homepage block is missing a required property."
        ),
        "impact": (
            f"A flat credit of {_t('flat_credit_5a_entity_fix')} leads a month, "
            "normalised against the client's own reference like every other rule. "
            "Nothing here is measurable per-page, so a measured estimate would be invented."
        ),
        "notes": (
            "One finding per run carrying every failing check, because they are one "
            "edit to one block — split per page it would be five actions for one "
            "forty-five-minute job. Growth action 5a."
        ),
    },
    "entity_fix": {
        "question": "Which rule key does `ai_readiness` file under?",
        "fires": "See `ai_readiness`.",
        "impact": "See `ai_readiness`.",
        "notes": "Same check, named twice: the signal the UI shows and the key the finding is stored under.",
    },
}


def _signals_in_code() -> set[str]:
    """Every name a finding can carry, however it is produced.

    Three spellings, because the engine has three: an `audit_signal` in a
    dict, one passed as a keyword, and a `gate`. Rule-key prefixes are
    included too — `internal_linking` and `serp_ctr` only ever appear
    there, and a scanner that missed them reported them as undocumented
    when they were the opposite.
    """
    src = "\n".join(path.read_text(encoding="utf-8") for path in SOURCES)
    names = set(
        re.findall(r'"audit_signal":\s*"([a-z0-9_]+)"', src)
        + re.findall(r'audit_signal="([a-z0-9_]+)"', src)
        + re.findall(r'"gate":\s*"([a-z0-9_]+)"', src)
        + re.findall(r'_rule_key\(\s*"([a-z0-9_]+)"', src)
        + re.findall(r'return "(keyword_[a-z0-9_]+)"', src)
        + re.findall(r'codes\.append\(\s*\(\s*"([a-z0-9_]+)"', src)
    )
    # Rule-key prefixes that are not checks: site-level wrappers and the
    # advisory Content Opp list.
    return names - {
        "technical",
        "technical_sitemap",
        "technical_robots",
        "search_opportunity",
        "conversion_path",
        "page_dropped",
        "tracking_silent",
        "link_reclaim",
        "ai_vis_kw",
        "ai_vis_prompt",
    }


#: The conversion gate carries its rule id on the finding rather than in
#: `ACTION_RULE_IDS`, because one gate produces two rules.
T1_GATE_RULES = {"conversion_page": "1a/1b"}


def _minutes_label(rule_id: str | None) -> str:
    if rule_id is None:
        return ""
    parts = [DEFAULT_MINUTES[r] for r in rule_id.split("/") if r in DEFAULT_MINUTES]
    if not parts:
        return ""
    return str(min(parts)) if len(set(parts)) == 1 else f"{min(parts)}–{max(parts)}"


def _row(signal: str) -> dict[str, str]:
    lever = SIGNAL_LEVERS.get(signal, "")
    if not lever:
        # Gates and rules that are not technical signals carry their lever
        # on the finding rather than in the map; fall back to the effort
        # table, which is keyed the same way.
        lever = {
            "tracking": "conversion_path",
            "tracking_partial": "conversion_path",
            "tracking_spike": "conversion_path",
            "site_conversion": "conversion_path",
            "converting_page_dropped": "conversion_path",
            "conversion_page": "conversion_path",
            "serp_ctr": "serp_ctr",
            "rank_push": "serp_ctr",
            "decaying_page": "serp_ctr",
            "internal_linking": "internal_linking",
            "keyword_not_ranking": "structured_data_ai",
            "keyword_fell_top5": "structured_data_ai",
            "keyword_fell_top10": "structured_data_ai",
            "prompt_not_cited": "structured_data_ai",
            "ai_crawlers_blocked": "structured_data_ai",
        }.get(signal, "technical_seo")
    # Core work is a property of the technical path only. `core_work` is set
    # in `_technical_finding` and nowhere else, so asking the technical
    # predicate about a gate returns a confident, wrong answer — it marked
    # every conversion check as upkeep.
    core = (
        signal in ROBOTS_ADVISORY_CODES
        or (signal in TECHNICAL_ACTIONS and is_core_work_signal(signal))
    )
    # Whether a check can spend an action is decided by one list, and this
    # column has to read it. Derived from `core_work` alone it said "growth
    # action" against `tracking` and `site_conversion`, neither of which
    # has a rule id and so neither of which can ever be one.
    rule_id = ACTION_RULE_IDS.get(signal) or T1_GATE_RULES.get(signal)
    if rule_id and not core:
        spends = "growth action"
    elif core:
        # Upkeep the monthly plan already pays for.
        spends = "core work"
    else:
        # Neither: a diagnostic, or an opportunity that needs a decision
        # before it can be a task. `tracking` says the measurement is
        # broken, which is something to fix, not an hour of work.
        spends = "reported"
    # No confidence, urgency, effort or S/M/L. They were four columns of
    # the old 0-100 ranking, and an action's cost is now the minutes its
    # own definition carries — a 15-minute CTA edit arriving as "M" because
    # its lever is scored medium is the sort of thing that made this table
    # misleading rather than merely redundant.
    return {
        "lever": LEVER_LABELS.get(lever, lever),
        "spends": spends,
        "blocking": "yes" if signal in INDEXATION_BLOCKING_SIGNALS else "",
        "rule": rule_id or "",
        "minutes": _minutes_label(rule_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()

    if args.audit:
        documented, in_code = set(CHECKS), _signals_in_code()
        missing = sorted(in_code - documented)
        stale = sorted(documented - in_code)
        print(f"{len(documented)} documented, {len(in_code)} emitted by the code")
        for name in missing:
            print(f"  UNDOCUMENTED  {name}")
        for name in stale:
            print(f"  not emitted    {name}")
        return 1 if missing else 0

    out: list[str] = [
        "# Every check, and what it is worth",
        "",
        "Generated by `python -m app.rules_catalog`. Which lever a check files",
        "under, whether it can spend a growth action, whether it preempts, and",
        "how long it takes are read out of the code; what each one checks is",
        "maintained beside it and audited with `--audit`.",
        "",
        "## What a growth action is",
        "",
        "A specific task of an hour or less, valued in **expected leads a month**,",
        "ranked by that number, and limited by the client's plan. Only the rules",
        "with an id below can be one. Everything else is reported: core work the",
        "plan already covers, or an opportunity that needs a decision first.",
        "",
        "```",
        "expected leads a month = raw lead estimate x 30 / window days",
        "                         x the rule's reliability prior",
        "```",
        "",
        "A rule with no honest clicks-to-leads model carries a flat credit",
        "instead, and says so on screen. Prompt gaps all carry the same credit",
        "by definition, so search volume breaks the tie.",
        "",
        f"Below {LIMITS['min_expected_leads_monthly']} leads a month an action is not offered. The floor is shown",
        "rather than applied silently, so it can be argued with.",
        "",
        "Three things stop a rule that could otherwise be an action: a gate",
        "upstream failed and its inputs cannot be trusted; the team has dismissed",
        "it three times across different pages; or it is core work.",
        "",
    ]

    by_lever: dict[str, list[str]] = {}
    for signal in CHECKS:
        by_lever.setdefault(_row(signal)["lever"], []).append(signal)

    for lever in sorted(by_lever):
        out += [f"## {lever}", ""]
        out += [
            "| Check | Spends | Preempts | Rule | Minutes |",
            "|---|---|---|---|---|",
        ]
        for signal in by_lever[lever]:
            row = _row(signal)
            out.append(
                f"| `{signal}` | {row['spends']} | {row['blocking']} "
                f"| {row['rule']} | {row['minutes']} |"
            )
        out.append("")
        for signal in by_lever[lever]:
            check = CHECKS[signal]
            out += [
                f"### `{signal}` — {check['question']}",
                "",
                f"**Fires when:** {check['fires']}",
                "",
                f"**Impact:** {check['impact']}",
                "",
            ]
            if check["notes"]:
                out += [f"**Note:** {check['notes']}", ""]

    out += [
        "## Causes a finding can report",
        "",
        "| Cause | Means |",
        "|---|---|",
    ]
    for name, text in CAUSES.items():
        out.append(f"| `{name}` | {text} |")
    out.append("")

    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
