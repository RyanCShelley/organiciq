"""Does a small embedding model map terms to pages better than token overlap?

The engine matches a term to a page today by shared words over the title and
the URL slug, with a penalty for words the page adds that the term did not
(`_best_page_for_prompt`). That is cheap and it is visibly thin: "What are
the best carbon fiber drone parts for racing" resolves to /what-is-carbon-fiber
on two shared words.

This asks whether MiniLM is worth a dependency, measured rather than assumed.

The yardstick is Search Console: for a query, the page it actually ranks.
That is not the same as the page that *should* own the term — where a site
ranks the wrong page, the yardstick is wrong too — but it is the only
observation available at this scale, and it is what the existing suggester
already uses where it has it.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
DATA = json.loads((HERE / "data.json").read_text())

# ── Baseline: the engine's current matcher, ported ──────────────────────────

_STOP = {
    "the", "and", "for", "with", "you", "your", "are", "can", "how", "what",
    "why", "who", "does", "did", "that", "this", "from", "its", "has", "have",
    "will", "was", "were", "they", "their", "there", "when", "where", "which",
    "into", "best", "most", "more", "than", "then", "over", "about",
}
_GENERIC = {"capabilities", "services", "service", "solutions", "page", "home", "index"}


def terms(text: str) -> set[str]:
    return {
        w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
        if w not in _STOP and len(w) > 2
    }


def baseline_pick(query: str, pages: list[dict]) -> str | None:
    """Shared words over title + URL slug, minus a penalty for extra words."""
    q = terms(query)
    if not q:
        return None
    scored = []
    for p in pages:
        slug = re.sub(r"^https?://[^/]+", "", p["url"]).replace("-", " ").replace("/", " ")
        cand = terms(p["title"]) | terms(slug)
        shared = q & cand
        if len(shared) < 2:
            continue
        extra = len(cand - q - _GENERIC)
        scored.append((len(shared) - 0.5 * extra, p["url"]))
    if not scored:
        return None
    scored.sort(key=lambda r: (-r[0], r[1]))
    return scored[0][1]


# ── Embeddings ──────────────────────────────────────────────────────────────


def page_document(p: dict) -> str:
    """What the model reads for a page.

    Title and description first because they are the page's own summary, then
    headings, which is the closest thing stored to what the page covers.
    """
    parts = [p["title"], p["desc"], " ".join(p["headings"]), " ".join(p["faqs"])]
    slug = re.sub(r"^https?://[^/]+", "", p["url"]).replace("-", " ").replace("/", " ")
    parts.append(slug)
    return " \n".join(x for x in parts if x).strip()[:2000]


def embed_all(texts: list[str], model) -> "list":
    import numpy as np

    vecs = np.array(list(model.embed(texts)), dtype="float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def main() -> int:
    import numpy as np
    from fastembed import TextEmbedding

    model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
    print("model: all-MiniLM-L6-v2 (ONNX, CPU)\n")

    for slug, d in DATA.items():
        pages = d["pages"]
        by_url = {p["url"]: p for p in pages}
        page_vecs = embed_all([page_document(p) for p in pages], model)
        urls = [p["url"] for p in pages]

        # ── Agreement test ──────────────────────────────────────────────
        # Only queries whose Search Console page is in the crawl: anything
        # else is unmatchable by construction and would flatter nothing.
        pairs = [g for g in d["gsc"] if g["url"] in by_url]
        pairs.sort(key=lambda g: -g["impr"])
        sample = pairs[:400]
        queries = [g["q"] for g in sample]
        q_vecs = embed_all(queries, model)
        sims = q_vecs @ page_vecs.T
        emb_top1 = [urls[i] for i in sims.argmax(axis=1)]
        emb_top3 = [{urls[i] for i in row.argsort()[-3:]} for row in sims]

        emb_hit = sum(1 for g, u in zip(sample, emb_top1) if u == g["url"])
        emb_hit3 = sum(1 for g, s in zip(sample, emb_top3) if g["url"] in s)
        base_picks = [baseline_pick(g["q"], pages) for g in sample]
        base_hit = sum(1 for g, u in zip(sample, base_picks) if u == g["url"])
        base_answered = sum(1 for u in base_picks if u is not None)

        n = len(sample)
        print(f"=== {slug} · {len(pages)} pages · {n} queries tested "
              f"(of {len(d['gsc'])} pairs, {len(pairs)} land on a crawled page)")
        print(f"  token overlap (today)  top-1 {base_hit:>4}/{n} = {base_hit/n:5.1%}"
              f"   · answered at all: {base_answered/n:.0%}")
        print(f"  MiniLM embeddings      top-1 {emb_hit:>4}/{n} = {emb_hit/n:5.1%}"
              f"   · top-3 {emb_hit3/n:.1%}")

        # ── The deliverable: proposed mappings for tracked keywords ─────
        kws = d["keywords"]
        k_vecs = embed_all([k["kw"] for k in kws], model)
        ksims = k_vecs @ page_vecs.T
        gsc_for = {g["q"].lower(): g["url"] for g in d["gsc"]}
        agree = seen = 0
        rows = []
        for k, row in zip(kws, ksims):
            order = row.argsort()[::-1]
            top, second = urls[order[0]], urls[order[1]]
            observed = gsc_for.get(k["kw"].lower())
            if observed and observed in by_url:
                seen += 1
                agree += int(observed == top)
            rows.append((k["kw"], k["group"], top, float(row[order[0]]),
                         second, observed))
        print(f"  tracked keywords: {len(kws)}; Search Console has an observed "
              f"page for {seen}; the model agrees on {agree}/{seen}"
              if seen else f"  tracked keywords: {len(kws)}; no observed pages")
        print("\n  proposed mappings (first 12):")
        for kw, grp, top, score, second, observed in rows[:12]:
            mark = "=" if observed == top else ("~" if observed else " ")
            print(f"   {mark} {kw[:34]:<35} {grp or '-':<22} "
                  f"{re.sub(r'^https?://[^/]+', '', top)[:40]:<41} {score:.2f}")
            if observed and observed != top:
                print(f"       GSC ranks: {re.sub(r'^https?://[^/]+', '', observed)[:60]}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
