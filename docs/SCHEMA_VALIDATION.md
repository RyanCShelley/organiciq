# Schema validation

The Machine readability audit reads each crawled page's JSON-LD through one validator, `apps/api/app/schema_validation`, built as four layers that do not depend on each other.

| Layer | Question | Module | Can be an error? |
|---|---|---|---|
| `schemaorg` | Is the markup valid Schema.org? | `schemaorg_rules.py` | Yes (a type or property that does not exist) |
| `graph` | Do the entities in the JSON-LD hold together? | `graph_rules.py` | Yes (no `@context`) |
| `google` | Does it meet what a Google Search feature needs? | `google_rules.py` | **Never.** Required and missing: warning. Recommended and missing: enhancement. A feature Google restricted or retired: informational |
| `recommendation` | What would make this kind of page say more? | `recommendation_rules.py` | **Never.** Enhancement |

Categories: **error** (technically wrong), **warning** (conflicts with the vocabulary, the page's own entities, or a Google feature's requirement), **enhancement** (worth adding, nothing is wrong), **informational** (valid, worth knowing). A property Google does not read is never an error.

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
