# Schema validation

The Machine readability audit reads each crawled page's JSON-LD through one validator, `apps/api/app/schema_validation`, built as four layers that do not depend on each other.

| Layer | Question | Module | Can be an error? |
|---|---|---|---|
| `schemaorg` | Is the markup valid Schema.org? | `schemaorg_rules.py` | Yes (a type or property that does not exist) |
| `graph` | Do the entities in the JSON-LD hold together? | `graph_rules.py` | Yes (no `@context`) |
| `google` | Does it meet what a Google Search feature needs? | `google_rules.py` | **Never.** Required and missing: warning. Recommended and missing: enhancement. A feature Google restricted or retired: informational |
| `baseline` | Does it meet SMA's own schema standard (the structured knowledge layer)? | `baseline_rules.py` | **Never.** Enhancement (a gap), or informational (retired or to be checked) |
| `recommendation` | What would make this kind of page say more? | `recommendation_rules.py` | **Never.** Enhancement |

Categories: **error** (technically wrong), **warning** (conflicts with the vocabulary, the page's own entities, or a Google feature's requirement), **enhancement** (worth adding, nothing is wrong), **informational** (valid, worth knowing). A property Google does not read is never an error.

## The SMA baseline

`baseline_rules.py` encodes the SMA schema baseline (v2, 26 Oct 2026): ten types in two layers, with the conditional third layer and the retired list in `google_rules.py`. It is SMA's standard, not a rule of Schema.org or Google, so it never reports an error, and each finding says so.

| Baseline item | Check |
|---|---|
| Every page is a WebPage in the site's graph | `WebPage` is expected on every kind of page (`expected.py`; a subtype counts); `baseline.webpage_is_part_of` |
| `about` on every content page and core service page | `baseline.about_missing` (kinds: editorial, documentation, service, productized service, FAQ) |
| `about`, `mentions`, `knowsAbout` linked to Wikipedia and Wikidata | `baseline.entity_link_wikidata`, `baseline.entity_link_wikipedia`, `baseline.about_not_entity`; a reference to a glossary term on the page counts as linked |
| Article with a Person author and an Organization publisher | `baseline.article_author`, `baseline.article_author_person`, `baseline.article_publisher` |
| Person identity | `baseline.person_property` (a standalone Person: url, jobTitle, worksFor, sameAs; an embedded author: url, sameAs) |
| WebSite with a publisher, no SearchAction | `baseline.website_publisher`; `baseline.search_action_retired` (informational) |
| Organization on the home and about pages | `baseline.org_id`, `baseline.org_property` (legalName, description, sameAs, contactPoint or telephone, address, foundingDate, founder, knowsAbout) |
| Glossary | `baseline.termset_terms`, `baseline.term_property`; `baseline.glossary_missing` once per site |
| Service pages | `baseline.service_property` (provider, serviceType, areaServed) |
| Breadcrumbs only where visible | `baseline.breadcrumb_visible` (informational, low confidence: it cannot be checked from markup) |

Not judged from markup: that markup matches the visible page, and that a Wikipedia or Wikidata link is the right concept. Those are the baseline's quarterly QA steps. The retired-feature rows added from the baseline (course, fact check, dataset, special announcement, practice problem, vehicle listing) carry `source` and have not been re-checked against Google's pages: re-check a row against its `doc` before relying on its date.

## Schema.org rules

The vocabulary is `app/schema_validation/data/schemaorg-<version>.json`, built from Schema.org's own release by `scripts/build_schema_vocab.py`. Nothing is a hand-kept property list.

* A property applies to a node if it is defined (`domainIncludes`) on **any `@type` the node has or any type above one** (`Service -> Intangible -> Thing`; `ImageObject -> MediaObject -> CreativeWork -> Thing`; multiple inheritance included).
* Does not exist, or differs from a term that does only by letter case: **error**.
* Defined, but not for this type's ancestry (`about` on a Service): **warning**. Schema.org's domains are *expected* types, not hard limits.
* Value of a kind the range does not list (a Product where an Organization is expected, `"yesterday"` for a date): **warning**, medium confidence.
* Deprecated or moved to the attic: **informational**.
* Types from another vocabulary, and prefixed properties (`og:title`): not judged.

## Graph rules

Every block, `@graph` member and nested object is read; identifiers are made absolute against the page address (`#organization` is `https://site/page#organization`). A value that is only `{"@id": ...}` is a reference.

* Schema.org term (`https://schema.org/InStock`): a value, not an entity.
* Another site's identifier: **external reference**, informational.
* This site's identifier that another crawled page defines: **defined elsewhere**, informational. Search engines read each page alone, so it is a robustness note.
* This site's identifier nothing defines: **dangling reference**, warning.
* Same `@id` defined twice: conflicting values are a warning, agreeing values informational. Also: no `@context` (error), remote context (warning), `mainEntity` pointing at the WebSite, `mainEntityOfPage` naming another page, `sameAs` that is not a URL, one organization under different `@id` values across the site.

## Adopting a new Schema.org release

```
python scripts/build_schema_vocab.py --version 31.0
```

Then set `VERSION` in `vocabulary.py` and run the tests. The validator never fetches the vocabulary at run time.

## Google rows

`google_rules.FEATURES` is data: one row per feature with its documentation page. Checked against the live pages on `REVIEWED`. Google does not version them, so re-check a row before changing it.

## Stored data

Nothing is stored. The audit is worked out from the crawled markup whenever the page is read, so a change to a rule applies to every client the next time the screen opens. Ignores saved by a person under the old cleanup wording no longer match and can be set again.
