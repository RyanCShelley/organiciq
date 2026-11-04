"""The playbook: the process and the outside guidance the copilot may cite.

Plain markdown files in `knowledge/`, split on `## ` headings. The core file is
small enough to sit in the system prompt; everything is searchable by tool so
the model can pull a section when a question needs outside guidance.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PLAYBOOK_DIR = Path(__file__).parent / "knowledge"
#: Always in the system prompt.
CORE_FILE = "oiq-process.md"

_WORD = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by for from how i in is it of on or our the to what when why with".split()
)


@dataclass(frozen=True)
class Section:
    source: str
    heading: str
    text: str


def _tokens(text: str) -> set[str]:
    # Trailing "s" dropped so action/actions and test/tests meet.
    return {
        w[:-1] if len(w) > 3 and w.endswith("s") else w
        for w in _WORD.findall(text.lower())
        if w not in _STOP and len(w) > 1
    }


@lru_cache(maxsize=1)
def load_sections() -> tuple[Section, ...]:
    sections: list[Section] = []
    for path in sorted(PLAYBOOK_DIR.glob("*.md")):
        heading = path.stem
        buf: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                if buf:
                    sections.append(Section(path.name, heading, "\n".join(buf).strip()))
                heading, buf = line[3:].strip(), []
            else:
                buf.append(line)
        if buf:
            sections.append(Section(path.name, heading, "\n".join(buf).strip()))
    return tuple(s for s in sections if s.text)


def core_text() -> str:
    return (PLAYBOOK_DIR / CORE_FILE).read_text(encoding="utf-8")


def search(query: str, limit: int = 3) -> list[Section]:
    """Sections ranked by the rarity of the query words they contain.

    A word found in few sections (Lift, CTR) counts for more than one found in
    most (plan, engine), and a heading hit counts triple. Crude on purpose: the
    corpus is a few dozen sections, and the model rewrites its own query when
    the first one misses. Swap for embeddings (fastembed is already installed)
    if the corpus outgrows this."""
    want = _tokens(query)
    sections = load_sections()
    if not want or not sections:
        return []
    bodies = [_tokens(s.text) for s in sections]
    heads = [_tokens(s.heading) for s in sections]
    n = len(sections)

    def idf(word: str) -> float:
        df = sum(1 for b, h in zip(bodies, heads) if word in b or word in h)
        return math.log(1 + n / df) if df else 0.0

    weights = {w: idf(w) for w in want}
    scored: list[tuple[float, Section]] = []
    for section, body, head in zip(sections, bodies, heads):
        score = sum(weights[w] * (1 + 3 * (w in head)) for w in want if w in body or w in head)
        if score:
            scored.append((score, section))
    scored.sort(key=lambda pair: -pair[0])
    return [s for _, s in scored[:limit]]
