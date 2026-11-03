# ruff: noqa: E501
# Long lines below are intentional — prompt template content must stay readable
# in its rendered form. Wrapping mid-instruction confuses the LLM.
"""Claude prompts for the per-page schema audit + markup generation.

Two distinct calls:

- ``build_audit_prompt`` — returns intent + visibility diagnosis + fix plan
  + suggested concept names. The system resolves concepts to Wikidata QIDs
  *after* this call; the LLM never invents QIDs itself.

- ``build_generate_prompt`` — given a set of analyst-approved QIDs, asks
  Claude to emit corrected JSON-LD using those QIDs as ``about`` sameAs
  links.

Both prompts explicitly forbid BreadcrumbList emission per project policy.
"""

from __future__ import annotations

import json
from typing import Any

# Maximum cleaned-content excerpt passed to the LLM (chars, not tokens).
# Keeps the prompt under ~3k tokens so cost stays predictable.
MAX_EXCERPT_CHARS = 6000


def _excerpt(content: str, limit: int = MAX_EXCERPT_CHARS) -> str:
    if not content:
        return ""
    if len(content) <= limit:
        return content
    return content[:limit] + " […truncated]"


def build_audit_prompt(
    *,
    page_url: str,
    page_type: str | None,
    title: str,
    cleaned_content: str,
    present_schema_types: list[str],
    parse_error_count: int,
    has_jsonld: bool,
    existing_jsonld: list[dict[str, Any]] | None = None,
) -> str:
    """Single-page audit prompt.

    Returns intent, diagnosis, fix plan, and a JSON array of concept names
    the system should look up on Wikidata.
    """
    schema_summary = {
        "has_jsonld": has_jsonld,
        "block_count": len(existing_jsonld or []),
        "present_types": present_schema_types,
        "parse_errors": parse_error_count,
    }
    existing_json_text = (
        json.dumps(existing_jsonld[:3], indent=2) if existing_jsonld else "(none)"
    )

    return f"""You are a Generative Engine Optimization (GEO) architect and Technical SEO auditor.

Your job for this single page:
(A) Determine the page intent (one word from: Home, Service, Blog, Product, Category, About, Contact, FAQ, Documentation, Landing, Generic).
(B) Diagnose schema visibility and structure issues.
(C) Recommend a prioritized fix plan.
(D) Suggest concept names to bridge the page to Wikidata entities for GEO visibility.

--- PAGE ---
URL: {page_url}
Title: {title}
Detected page type (from URL + schema heuristics): {page_type or "unknown"}

--- EXISTING JSON-LD SUMMARY ---
{json.dumps(schema_summary, indent=2)}

--- EXISTING JSON-LD (first 3 blocks) ---
{existing_json_text}

--- PAGE CONTENT EXCERPT ---
{_excerpt(cleaned_content)}

--- HARD RULES ---
1. DO NOT output JSON-LD in this response. Only the analysis below.
2. DO NOT invent Wikidata QIDs. Output concept NAMES only — the system looks up QIDs.
3. DO NOT recommend BreadcrumbList anywhere. It is excluded from this tool by project policy.
4. Suggested concepts must be the page's CORE subjects (3–7 items), not navigation chrome.

--- RESPONSE FORMAT ---
Respond with ONE JSON object, no prose before or after, no markdown fencing. Exact shape:

{{
  "intent": "Service",
  "intent_explanation": "1-2 sentences explaining why this intent was chosen, referencing specific page evidence.",
  "diagnosis": [
    "Bullet 1 — schema visibility issue or strength.",
    "Bullet 2 — entity-relationship gap (mainEntity, isPartOf, etc.)",
    "Bullet 3 — specificity or hierarchy issue.",
    "Bullet 4 — Wikidata entity-bridge opportunity.",
    "Bullet 5 — any optional issue worth surfacing."
  ],
  "fix_plan": [
    "Step 1 (highest leverage) — concrete action.",
    "Step 2 — next concrete action.",
    "Step 3 — etc."
  ],
  "suggested_concepts": ["Concept Name 1", "Concept Name 2", "Concept Name 3"]
}}

Notes:
- Keep diagnosis bullets focused and specific. Reference the existing schema where relevant.
- Fix plan steps should be actionable (mention property names, target node types).
- Use proper-noun casing for concept names (e.g. "Search Engine Optimization", not "search engine optimization").
"""


def build_generate_prompt(
    *,
    page_url: str,
    page_type: str | None,
    title: str,
    cleaned_content: str,
    site_origin: str,
    organization_name: str | None,
    approved_qids: list[dict[str, str]],
    existing_jsonld: list[dict[str, Any]] | None = None,
) -> str:
    """Markup-generation prompt.

    ``approved_qids`` is a list of ``{"name": "...", "qid": "Q..."}`` dicts —
    these are the ONLY sameAs entities the LLM may emit on ``about``.
    """
    qid_lines = (
        "\n".join(
            f'- {q["name"]}: https://www.wikidata.org/wiki/{q["qid"]}'
            for q in approved_qids
        )
        if approved_qids
        else "(no approved QIDs — omit the 'about' array entirely)"
    )
    existing_json_text = (
        json.dumps(existing_jsonld[:3], indent=2) if existing_jsonld else "(none)"
    )

    return f"""You are a Generative Engine Optimization (GEO) architect generating corrected JSON-LD for a single page.

--- PAGE ---
URL: {page_url}
Title: {title}
Detected page type: {page_type or "unknown"}
Site origin: {site_origin}
Organization name (if known): {organization_name or "(infer from page content)"}

--- APPROVED WIKIDATA QIDs (USE ONLY THESE) ---
{qid_lines}

--- EXISTING JSON-LD (first 3 blocks, for reference) ---
{existing_json_text}

--- PAGE CONTENT EXCERPT ---
{_excerpt(cleaned_content)}

--- ABSOLUTE RULES ---
1. Output ONE JSON object with shape: {{"@context": "https://schema.org", "@graph": [...]}}.
2. DO NOT emit BreadcrumbList anywhere in the output. DO NOT add a 'breadcrumb' property to WebPage. This is a hard project requirement.
3. Use ONLY the approved Wikidata QIDs above. DO NOT invent QIDs. If none are relevant to the page, omit the 'about' array.
4. DO NOT include markdown fencing or prose. Return ONLY the JSON object.

--- STRUCTURE RULES ---
- "logo" MUST be an ImageObject: {{"@type": "ImageObject", "url": "<url>"}} — never a bare string.
- Include an Organization node at @id "<site_origin>#organization".
- Include a WebSite node at @id "<site_origin>#website" with publisher → #organization.
- Include a WebPage node at @id "<page_url>#webpage" with isPartOf → #website.
- Place 'about' (the Wikidata entity bridge) on the WebPage ONLY — never on Service or Organization.
- 'about' entries use the shape: {{"@type": "Thing", "name": "<approved name>", "sameAs": "https://www.wikidata.org/wiki/<approved QID>"}}.
- If the page is a Service or Product, link WebPage.mainEntity → that Service/Product node by @id.
- Service node uses "provider" → #organization (provider IS valid on Service).
- ProfessionalService / LocalBusiness / Organization use "parentOrganization" instead of "provider".
- For service URLs: Service.url MUST point to the page being audited (not the homepage).
- Use @id references rather than duplicating organization/website data across nodes.

--- VALID PROPERTIES (do not invent fields) ---
Stick to canonical schema.org properties for each @type. If unsure, omit the field rather than guessing.

Respond with the JSON-LD object only.
"""
