"""Builds the compact Schema.org vocabulary the schema validator reads.

    python scripts/build_schema_vocab.py [--version 30.1] [--source path-or-url]

The source is Schema.org's own machine-readable release (schemaorg-current-https.jsonld). The output keeps only what validation needs:
every type with its parents and whether it is deprecated or pending, every property with the types it is defined on (domainIncludes),
the types its value may be (rangeIncludes), and what superseded it. Commit the result; the validator never fetches the vocabulary at run time,
so a release is adopted deliberately, with the tests as the check.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path

URL = "https://schema.org/version/latest/schemaorg-current-https.jsonld"
OUT = Path(__file__).resolve().parents[1] / "app" / "schema_validation" / "data"
DATATYPES = {"Text", "URL", "Number", "Integer", "Float", "Boolean", "Date", "DateTime", "Time", "DataType", "CssSelectorType", "XPathType", "PronounceableText"}


def many(value) -> list[dict]:
    return value if isinstance(value, list) else ([value] if value else [])


def name(ref: dict | str) -> str:
    iri = ref["@id"] if isinstance(ref, dict) else ref
    return iri.split(":", 1)[1] if iri.startswith("schema:") else iri


def is_schema(ref) -> bool:
    return (ref["@id"] if isinstance(ref, dict) else ref).startswith("schema:")


def status(node: dict) -> str | None:
    """'deprecated' (superseded or in the attic), 'pending' (in the pending area) or None."""
    part = node.get("schema:isPartOf")
    part_id = (part.get("@id") if isinstance(part, dict) else part) or ""
    if "attic" in part_id or node.get("schema:supersededBy"):
        return "deprecated"
    if "pending" in part_id:
        return "pending"
    return None


def build(graph: list[dict]) -> dict:
    types: dict[str, dict] = {}
    props: dict[str, dict] = {}
    by_id = {n["@id"]: n for n in graph}
    for n in graph:
        kinds = n["@type"] if isinstance(n["@type"], list) else [n["@type"]]
        if not n["@id"].startswith("schema:"):
            continue
        label = name(n["@id"])
        if "rdfs:Class" in kinds:
            entry = {"parents": sorted(name(p) for p in many(n.get("rdfs:subClassOf")) if is_schema(p))}
            if label in DATATYPES or "schema:DataType" in kinds:
                entry["datatype"] = True
            if s := status(n):
                entry["status"] = s
            if sup := [name(x) for x in many(n.get("schema:supersededBy"))]:
                entry["superseded_by"] = sup
            types[label] = entry
        elif "rdf:Property" in kinds:
            entry = {
                "domains": sorted(name(d) for d in many(n.get("schema:domainIncludes")) if is_schema(d)),
                "ranges": sorted(name(r) for r in many(n.get("schema:rangeIncludes")) if is_schema(r)),
            }
            if s := status(n):
                entry["status"] = s
            if sup := [name(x) for x in many(n.get("schema:supersededBy"))]:
                entry["superseded_by"] = sup
            if sub := [name(x) for x in many(n.get("rdfs:subPropertyOf")) if is_schema(x)]:
                entry["sub_property_of"] = sub
            props[label] = entry
    # Enumeration members are typed by their enumeration, so they are not classes of their own here.
    for label, t in types.items():
        t["parents"] = [p for p in t["parents"] if p in types]
    return {"types": dict(sorted(types.items())), "properties": dict(sorted(props.items()))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--source", default=URL)
    args = ap.parse_args()
    if args.source.startswith("http"):
        with urllib.request.urlopen(args.source, timeout=120) as r:  # noqa: S310 - a fixed, published vocabulary
            doc = json.load(r)
    else:
        doc = json.loads(Path(args.source).read_text())
    vocab = build(doc["@graph"])
    vocab = {"version": args.version, "source": URL, "types_count": len(vocab["types"]), "properties_count": len(vocab["properties"]), **vocab}
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / f"schemaorg-{args.version}.json"
    target.write_text(json.dumps(vocab, separators=(",", ":"), sort_keys=False))
    print(f"{target}: {vocab['types_count']} types, {vocab['properties_count']} properties, {target.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
