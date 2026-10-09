# Can a small embedding model map terms to pages?

Run 9 Oct 2026 against SMA Marketing and Element 6 Composites, live data.
`match.py` is the prototype; it reads an export of pages, tracked keywords
and Search Console query→page pairs. The export is client data and is not
committed — regenerate it with the script in the commit message.

**Model:** `sentence-transformers/all-MiniLM-L6-v2`, 22M params, Apache 2.0,
run through ONNX via `fastembed`. No torch. 184 MB venv, ~38 s for 538 pages
and 800 queries on a laptop CPU.

## The yardstick, and what it does not prove

For each query, Search Console reports the page that actually ranks. That is
an observation, and it is what the existing suggester already uses where it
has it. It is **not** the page that *should* own the term — where a site
ranks the wrong page, the yardstick is wrong too — so treat agreement as "can
the model find the page this site already uses for this subject", not as
"is the mapping correct".

Only queries whose Search Console page is in the crawl were tested; anything
else is unmatchable by construction.

## Result

| | SMA (478 pages) | Element 6 (60 pages) |
|---|---|---|
| Token overlap — what the engine does today | **32.8%** top-1 | **25.2%** top-1 |
| MiniLM embeddings | **72.2%** top-1 · 84.0% top-3 | **36.8%** top-1 · 56.2% top-3 |

Embeddings roughly double the agreement on SMA. On Element 6 the gain is
real but much smaller.

## Why Element 6 is weaker — and the hypothesis that was wrong

First guess: Element 6's crawl predates the `sections` capture, so the model
reads 190 characters per page against SMA's 458. Tested by stripping headings
from SMA: **72.2% → 71.0%.** Headings are not the cause.

The actual cause is that Element 6's pages are near-duplicates of each other.

| | mean page-to-page similarity | margin, best page vs runner-up |
|---|---|---|
| SMA | 0.398 | 0.079 |
| Element 6 | **0.594** | **0.034** |

Element 6 is a carbon-fibre manufacturer and all 60 pages are about carbon
fibre. The model is not failing; the pages genuinely are hard to tell apart,
and so would a person be.

## The useful part: the model knows when it is guessing

Propose only when the top page beats the runner-up by at least M.

**SMA**

| margin | proposes on | of all terms | correct |
|---|---|---|---|
| 0.00 | 400 | 100% | 72.2% |
| 0.05 | 229 | 57% | **93.0%** |
| 0.10 | 133 | 33% | **98.5%** |
| 0.15 | 59 | 15% | 100% |

**Element 6**

| margin | proposes on | of all terms | correct |
|---|---|---|---|
| 0.00 | 400 | 100% | 36.8% |
| 0.05 | 85 | 21% | 61.2% |
| 0.10 | 18 | 4% | 72.2% |

The margin is a strong confidence signal. On a site with distinguishable
pages it fills most of the map at high precision; on a site of near-identical
pages it correctly goes quiet. That is the behaviour to build: **propose above
a margin, and hand everything else to a person with the top three.**

## What this means for the build

1. **Embeddings are worth the dependency** — roughly double the agreement, at
   38 s per client on CPU, with no torch.
2. **The observation still wins.** Where Search Console shows a page for a
   term, use it. Embeddings fill the gap for terms that do not rank yet,
   which is the V1 and V4 case.
3. **Per-client margin, not a global one.** A single threshold would be too
   loose for Element 6 and too tight for SMA. Calibrate per client against
   that client's own Search Console pairs — every client with query×page data
   can be measured exactly as above.
4. **Low margin is a `confidence_reason`,** not a silent guess. It maps onto
   the spec's existing `no_target_mapping` code.
5. **`role` and `priority` stay human.** Nothing here proposes them.

## Caveat worth repeating

On SMA's tracked keywords the model agreed with Search Console on 8 of 26.
Several disagreements look like the model being right: for "content marketing
firm" it proposes `/capabilities/content-marketing` while Search Console
ranks `/blog/best-content-marketing-agencies-florida`. A capability page
should own a commercial term; a blog post ranking for it is the V-6
re-homing case. So low agreement on *tracked* terms is partly the model
detecting that the wrong page ranks — which is a feature, and also means
tracked-term agreement is the wrong number to tune on. Tune on the
high-impression query sample above.
