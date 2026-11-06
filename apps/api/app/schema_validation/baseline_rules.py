"""Layer 5: the SMA schema baseline (v2, 26 Oct 2026): the structured knowledge layer every client site gets.

The baseline is SMA's own standard, not a rule of Schema.org or Google, and the layers it sits beside say so: nothing here is an error and nothing here is a
Google requirement. A gap against it is an **enhancement** ("the markup would say more"), and things the baseline tells us to leave alone or to check are
**informational**. It asks for ten types in two layers (the conditional third layer, and the types Google retired, are in `google_rules`):

* Layer 1, the entity foundation, on every site: Organization (one fixed `@id`, the facts that identify it), WebSite (`publisher`, no SearchAction), WebPage on
  every page (`isPartOf`, `about`, `mentions`) and Person for authors.
* Layer 2, the knowledge structure, on the pages that hold that content: Article/BlogPosting (author Person, publisher Organization), `about` and `mentions`
  linked to a Wikipedia URL **and** a Wikidata item, FAQPage, HowTo, DefinedTermSet and DefinedTerm.

What each check reads is the page's own markup, with `@id` references followed within the page. Whether markup matches the visible page, and whether a
Wikipedia or Wikidata link points at the right concept, cannot be judged from markup alone: those are the quarterly QA steps in the baseline, and the findings
say so instead of guessing.
"""

from __future__ import annotations

from typing import Any

from app.schema_validation import findings as F
from app.schema_validation.graph import Graph, Node, absolute, as_list
from app.schema_validation.schemaorg_rules import snippet
from app.schema_validation.vocabulary import Vocabulary

VERSION = "SMA schema baseline v2 (26 Oct 2026)"

#: Kinds of page that hold content and so carry `about` (the baseline: every content page and core service page).
CONTENT_KINDS = {"editorial", "documentation", "service", "productized_service", "faq"}
#: The facts that identify the organization, asked of the home or about page. Name, URL and logo are read by the brand-entity checks.
ORG_PROPERTIES = (
    ("legalName", "legalName", "the registered name"),
    ("description", "description", "what the company does, in a sentence or two"),
    ("sameAs", "sameAs", "the company's LinkedIn, YouTube, Clutch, Crunchbase and, if they exist, Wikidata and Wikipedia pages"),
    ("contactPoint|telephone", "contactPoint", "a contact point or telephone number"),
    ("address", "address", "the postal address"),
    ("foundingDate", "foundingDate", "the year or date it was founded"),
    ("founder", "founder", "who founded it (a Person)"),
    ("knowsAbout", "knowsAbout", "the core topics, each linked to Wikipedia and Wikidata"),
)
LINKED_PROPERTIES = ("about", "mentions", "knowsAbout")
_DOC = "https://schema.org/"


def _tn(vocab: Vocabulary, node: Node) -> list[str]:
    return [t for t in (vocab.type_name(x) for x in node.types) if t]


def _is(vocab: Vocabulary, node: Node, family: str) -> bool:
    return any(vocab.is_a(t, family) for t in _tn(vocab, node))


def _present(data: dict[str, Any], spec: str) -> bool:
    return any(data.get(p) not in (None, "", [], {}) for p in spec.split("|"))


def _target(graph: Graph, value: Any) -> tuple[dict[str, Any] | None, Node | None]:
    """The data a value stands for: itself when embedded, the node it references when it is only an @id (None when that is not on the page)."""
    if not isinstance(value, dict):
        return None, None
    if set(value) == {"@id"}:
        n = graph.get(absolute(value["@id"], graph.url))
        return (n.data, n) if n else (None, None)
    return value, None


def _kinds(vocab: Vocabulary, data: dict[str, Any]) -> list[str]:
    return [t for t in (vocab.type_name(x) for x in as_list(data.get("@type")) if isinstance(x, str)) if t]


def _links(data: dict[str, Any]) -> tuple[bool, bool]:
    """Does sameAs carry a Wikidata item, and a Wikipedia page?"""
    urls = [u.lower() for u in as_list(data.get("sameAs")) if isinstance(u, str)]
    return any("wikidata.org" in u for u in urls), any("wikipedia.org" in u for u in urls)


def check(graph: Graph, vocab: Vocabulary, page_type: str | None) -> list[F.Finding]:
    out: list[F.Finding] = []

    def add(node: Node | None, rule: str, category: str, *, prop: str | None, type_: str | None, title: str, message: str, explanation: str, recommendation: str,
            doc: str, evidence: Any = None, confidence: str = "high") -> None:
        out.append(F.Finding(
            url=graph.url, layer="baseline", rule_id=f"baseline.{rule}", category=category, type=type_, property=prop, entity_id=(node.id or node.raw_id) if node else None,
            title=title, message=message, explanation=explanation + f" This is part of the {VERSION}, not a requirement of Schema.org or Google.", recommendation=recommendation,
            doc=doc, evidence=evidence, confidence=confidence,
        ))

    top = [n for n in graph.nodes if n.top_level]
    pages = [n for n in top if _is(vocab, n, "WebPage")]

    # ── layer 1: the page belongs to the site, and says what it is about ─────
    for p in pages:
        if not p.data.get("isPartOf"):
            add(p, "webpage_is_part_of", F.ENHANCEMENT, prop="isPartOf", type_="WebPage", title="WebPage does not say which WebSite it is part of",
                message="The WebPage has no isPartOf", explanation="isPartOf ties each page to the site, and through the site to the organization that publishes it, so the page is one connected graph rather than a loose node.",
                recommendation='Add "isPartOf": {"@id": "<the WebSite @id>"} to the WebPage.', doc=_DOC + "isPartOf", evidence={"@type": p.types})
    if page_type in CONTENT_KINDS:
        subjects = [n for n in top if _is(vocab, n, "WebPage") or _is(vocab, n, "Article")]
        if subjects and not any(_present(n.data, "about") for n in subjects):
            n = subjects[0]
            add(n, "about_missing", F.ENHANCEMENT, prop="about", type_="/".join(_tn(vocab, n)), title="Content page names nothing as what it is about",
                message=f"The page reads as a {(page_type or '').replace('_', ' ')} page and neither its WebPage nor its Article says what it is about",
                explanation="about names the page's one to three main topics as entities, each linked to Wikipedia and Wikidata, so a machine can tell which meaning of a term the page uses.",
                recommendation="Add about with the page's main topics, each a Thing with a name and sameAs links to its Wikipedia page and Wikidata item.", doc=_DOC + "about", evidence={"@type": n.types})

    # ── entity links: about, mentions, knowsAbout, and a DefinedTerm's own sameAs ──
    def link_check(owner: Node, prop: str, data: dict[str, Any], label: str) -> None:
        wd, wp = _links(data)
        kind = "/".join(_kinds(vocab, data)) or "Thing"
        for missing, rule, where, ok in (("Wikidata item", "entity_link_wikidata", "wikidata.org", wd), ("Wikipedia page", "entity_link_wikipedia", "wikipedia.org", wp)):
            if ok:
                continue
            add(owner, rule, F.ENHANCEMENT, prop=prop, type_=kind, title=f"'{prop}' entities are not linked to a {missing}",
                message=f"{label} in '{prop}' has no sameAs link to a {missing}",
                explanation="Linking each topic to a Wikidata item (language-neutral and stable) and to its Wikipedia page is what lets a machine resolve a term to one concept. "
                "Not every concept has both: where one does not exist there is nothing to add, and a wrong link is worse than none, so check that the link is the right concept.",
                recommendation=f"Add the {missing} to sameAs if the concept has one ({where}), after confirming it is the same concept.", doc=_DOC + "sameAs", evidence={"name": data.get("name"), "sameAs": data.get("sameAs")},
                confidence="medium")

    for n in graph.nodes:
        for prop in LINKED_PROPERTIES:
            for v in as_list(n.data.get(prop)):
                if isinstance(v, str):
                    add(n, "about_not_entity", F.ENHANCEMENT, prop=prop, type_="/".join(_tn(vocab, n)) or None, title=f"'{prop}' holds text, not an entity",
                        message=f"'{prop}' is the text '{snippet(v, 60)}'", explanation="about, mentions and knowsAbout name things. Plain text says nothing about which thing, so a machine cannot link it to a concept.",
                        recommendation="Replace it with a node that has a name and sameAs links to its Wikipedia page and Wikidata item.", doc=_DOC + prop, evidence={prop: snippet(v)})
                    continue
                data, target = _target(graph, v)
                if data is None or target is not None and _is(vocab, target, "DefinedTerm"):
                    continue  # a reference to something not on this page cannot be judged; one to a glossary term on this page is the internal link the baseline asks for
                if any(vocab.is_a(t, "DefinedTerm") for t in _kinds(vocab, data)) and data.get("inDefinedTermSet"):
                    continue
                link_check(n, prop, data, f"'{data.get('name') or 'an entity'}'")
        if _is(vocab, n, "DefinedTerm") and n.top_level:
            link_check(n, "sameAs", n.data, f"The term '{n.data.get('name') or n.id}'")

    # ── Article: who wrote it and who published it ───────────────────────────
    for n in top:
        if not _is(vocab, n, "Article"):
            continue
        t = "/".join(_tn(vocab, n))
        authors = as_list(n.data.get("author"))
        kinds = [k for a in authors for d in [_target(graph, a)[0]] if d is not None for k in _kinds(vocab, d)]
        if not authors:
            add(n, "article_author", F.ENHANCEMENT, prop="author", type_=t, title="Article has no author", message=f"The {t} has no author",
                explanation="An author who is a real, identifiable person ties the content to someone with credentials (E-E-A-T).", recommendation="Add author as a Person with a name and a link to their profile page.",
                doc=_DOC + "author", evidence={"@type": n.types})
        elif authors and not any(vocab.is_a(k, "Person") for k in kinds) and all(_target(graph, a)[0] is not None or isinstance(a, str) for a in authors):
            add(n, "article_author_person", F.ENHANCEMENT, prop="author", type_=t, title="Article's author is not a Person",
                message="The author is text or an organization, not a Person", explanation="The baseline asks for a Person (the real author), referenced from every article, so the page is tied to someone with credentials.",
                recommendation="Make author a Person node with name, url and sameAs.", doc=_DOC + "author", evidence={"author": snippet(n.data.get("author"))})
        pubs = [d for v in as_list(n.data.get("publisher")) for d in [_target(graph, v)[0]] if d is not None]
        if not pubs or not any(vocab.is_a(k, "Organization") for d in pubs for k in _kinds(vocab, d)):
            add(n, "article_publisher", F.ENHANCEMENT, prop="publisher", type_=t, title="Article does not name its publisher as an Organization",
                message="publisher is missing or is not an Organization", explanation="publisher ties the article to the organization entity, so the content and the company are one graph.",
                recommendation='Add "publisher": {"@id": "<the Organization @id>"}.', doc=_DOC + "publisher", evidence={"publisher": snippet(n.data.get("publisher"))})

    # ── Person: the identity behind an author ────────────────────────────────
    for n in graph.nodes:
        if not _is(vocab, n, "Person"):
            continue
        wanted = ("url", "jobTitle", "worksFor", "sameAs") if n.top_level else ("url", "sameAs")
        for prop in wanted:
            if not _present(n.data, prop):
                add(n, "person_property", F.ENHANCEMENT, prop=prop, type_="Person", title=f"Person has no '{prop}'", message=f"The Person '{n.data.get('name') or n.id}' has no {prop}",
                    explanation="An author or expert is useful to a machine when it can tell who they are: their profile page, role, employer and profiles elsewhere.",
                    recommendation={"url": "Link to the person's profile page on the site.", "sameAs": "Add their LinkedIn and other profile URLs.", "jobTitle": "Add their job title.",
                                    "worksFor": 'Add "worksFor": {"@id": "<the Organization @id>"}.'}[prop], doc=_DOC + prop, evidence={"name": n.data.get("name")}, confidence="medium")

    # ── WebSite: named, published by the organization, no search box ─────────
    for n in top:
        if not _is(vocab, n, "WebSite"):
            continue
        if not _present(n.data, "publisher"):
            add(n, "website_publisher", F.ENHANCEMENT, prop="publisher", type_="WebSite", title="WebSite does not name its publisher", message="The WebSite has no publisher",
                explanation="publisher ties the site to the Organization entity every other node refers back to.", recommendation='Add "publisher": {"@id": "<the Organization @id>"}.', doc=_DOC + "publisher",
                evidence={"@type": n.types})
        for a in as_list(n.data.get("potentialAction")):
            if isinstance(a, dict) and any(vocab.is_a(k, "SearchAction") for k in _kinds(vocab, a)):
                add(n, "search_action_retired", F.INFORMATIONAL, prop="potentialAction", type_="WebSite", title="SearchAction on the WebSite: Google retired the sitelinks search box",
                    message="The WebSite carries a SearchAction", explanation="Google retired the sitelinks search box in 2024, so this markup no longer earns a result. It is valid Schema.org and harmless.",
                    recommendation="No change is required. The baseline leaves it out of new markup; remove it when the template is next edited.", doc=F.GOOGLE_GALLERY, evidence={"potentialAction": snippet(a)})
                break

    # ── Organization on the home and about pages: the facts that identify it ──
    if page_type in ("homepage", "about"):
        orgs = [n for n in top if _is(vocab, n, "Organization")]
        if orgs:
            o = orgs[0]
            t = "/".join(_tn(vocab, o))
            if not o.id:
                add(o, "org_id", F.ENHANCEMENT, prop="@id", type_=t, title="Organization has no @id", message="The Organization has no @id",
                    explanation="One fixed @id on the organization is how every page's markup points back to the same entity.", recommendation='Give it a stable @id such as "https://example.com/#organization" and use it on every page.',
                    doc=_DOC + "Organization")
            for spec, prop, what in ORG_PROPERTIES:
                if not _present(o.data, spec):
                    add(o, "org_property", F.ENHANCEMENT, prop=prop, type_=t, title=f"Organization has no '{prop}'", message=f"The Organization on this page has no {prop}",
                        explanation="These are the facts that let a machine resolve who the company is.", recommendation=f"Add {prop}: {what}.", doc=_DOC + prop, evidence={"@type": o.types})

    # ── knowledge structure: glossary ────────────────────────────────────────
    for n in top:
        if _is(vocab, n, "DefinedTermSet") and not _present(n.data, "hasDefinedTerm"):
            add(n, "termset_terms", F.ENHANCEMENT, prop="hasDefinedTerm", type_="DefinedTermSet", title="DefinedTermSet lists no terms", message="The glossary has no hasDefinedTerm",
                explanation="The set declares the company's official vocabulary in one place; without its terms it declares nothing.", recommendation="List each term in hasDefinedTerm, by @id.", doc=_DOC + "hasDefinedTerm")
        if _is(vocab, n, "DefinedTerm"):
            for prop, what in (("inDefinedTermSet", "the glossary's @id"), ("description", "the definition shown on the page")):
                if not _present(n.data, prop):
                    add(n, "term_property", F.ENHANCEMENT, prop=prop, type_="DefinedTerm", title=f"DefinedTerm has no '{prop}'", message=f"The term '{n.data.get('name') or n.id}' has no {prop}",
                        explanation="Each term has one canonical, linked definition that the whole site refers back to.", recommendation=f"Add {prop}: {what}.", doc=_DOC + prop)

    # ── conditional types: what a page of that kind needs to say ─────────────
    if page_type in ("service", "productized_service"):
        for n in top:
            if _is(vocab, n, "Service"):
                for prop, what in (("provider", 'the Organization: {"@id": "<the Organization @id>"}'), ("serviceType", "what the service is"), ("areaServed", "where it is offered")):
                    if not _present(n.data, prop):
                        add(n, "service_property", F.ENHANCEMENT, prop=prop, type_="/".join(_tn(vocab, n)), title=f"Service has no '{prop}'", message=f"The Service has no {prop}",
                            explanation="A service page's Service says what is offered, by whom and where, in terms a machine can read.", recommendation=f"Add {prop}: {what}.", doc=_DOC + prop, confidence="medium")
    for n in top:
        if _is(vocab, n, "BreadcrumbList"):
            add(n, "breadcrumb_visible", F.INFORMATIONAL, prop=None, type_="BreadcrumbList", title="BreadcrumbList: the page must show the same trail",
                message="The page carries BreadcrumbList markup", explanation="The baseline allows breadcrumb markup only where the site shows a visible breadcrumb trail, and the markup must mirror it exactly. "
                "Markup without a visible trail is what triggers validation errors. This cannot be checked from the markup alone.", recommendation="Confirm the page shows this trail. If the theme shows none, turn breadcrumbs off in the template.",
                doc=F.GOOGLE_GALLERY, confidence="low")
            break
    return out
