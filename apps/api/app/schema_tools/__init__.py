"""Schema tools, ported from the Topic Hub tool (github.com/RyanCShelley/topic-hub, `schema_audit` and `page_type`).

Kept as close to the original as possible so a fix in one can be carried to the other:

- `expected`: the JSON-LD each kind of page should carry (required, recommended, accepted substitutes).
- `page_type`: what kind of page a URL is, from its address and the markup it already carries.
- `transforms`: the deterministic cleanup of existing JSON-LD, and the list of corrections it finds.
- `wikidata`: looking a concept up on Wikidata so it can be linked from the markup as an entity.
- `prompts`: the two Claude prompts (audit a page, generate corrected markup).

Breadcrumb markup is excluded throughout, by the same project rule.
"""
