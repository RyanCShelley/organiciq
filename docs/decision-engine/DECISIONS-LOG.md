# Decisions taken outside the spec

Things settled in conversation that the spec does not cover, recorded so the
reasoning survives. Dated, because several rest on measurements that will go
stale.

---

## 9 Oct 2026 — Keep the in-house crawler; revisit if bot protection bites

**Considered:** replacing `app/ingestion/crawler/` with advertools (Scrapy) or
crawl4ai (Playwright).

**Decided:** keep it, and log the trigger that would change the answer.

The honest case for advertools is that its rate limiting is better than ours.
Scrapy's `AUTOTHROTTLE` has had a decade of use; our first version of the same
idea backed off correctly and never recovered — a crawl of acctek.com fetched
106 pages with nothing refused and still finished at the 10-second ceiling.

But advertools would replace `fetch.py` only. The decision engine's inputs come
from `parse.py`, and none of them is something a general crawler produces:

- `sections` — a heading paired with its first paragraph, which is the whole
  basis of 3a
- `faq_questions`
- `in_content` link classification and the template-prevalence rule
- `conversion_elements`
- `says_not_found` — soft 404s

crawl4ai is a worse fit than advertools, not a better one: it renders with
Playwright and emits markdown for LLM ingestion, where we deliberately do not
render JS and store a structured shape.

**Revisit when bot protection becomes the problem rather than politeness.**
Two signs of it already: acctek.com returned 403 to a laptop and 200 to the
Railway container for the same URL on the same day, and Aquaman's host serves
challenge pages. Rotating agents, proxies and session handling is where
Scrapy's middleware genuinely beats anything hand-written.

---

## 9 Oct 2026 — DataForSEO for SERP features, not SerpApi

**Need:** spec §7 lists "all SERP features, held or not" as blocked, which
blocks **V-5** (extractable structure) and **T-2** (match the SERP format).
SE Ranking gives `earned_serp_features` on all 769 tracked keywords — what the
client *won*. What is *on* the SERP lives in `FactSerDomainKeyword.serp_features`,
which has **6 rows across all clients**.

**Volume:** 480 pulls a month at the spec's "top 20 targets per client", or 769
for every tracked keyword.

| | at 769/month | billing |
|---|---|---|
| DataForSEO | ~$0.46 standard queue, ~$1.54 live | pay-as-you-go, $50 minimum deposit |
| SerpApi | $25/month Starter, 1,000 searches | no overage; exceeding renews the plan early |

**Decided: DataForSEO.** The price gap matters less than the coverage: it also
sells keyword difficulty, which is the other blocked input — the `Reach` factor
in Decision 2 needs it and we have it for 2 of 24 clients. One integration
unblocks V-5, T-2 and the scoring factor. SerpApi covers only the SERP half.

Prices are from third-party comparison sites, several of which sell competing
APIs; neither vendor's own pricing page was reachable. Confirm before
depositing.

**Priority: unchanged.** This is P2 in the spec and stays there. V-5 and T-2 are
two of twelve actions, in branches that are not the constraint for most clients.

### Free fix, independent of the purchase

`_ai_overview_queries` (`lever_engine.py`) reads `FactSerDomainKeyword`, which
has 6 rows. `earned_serp_features` shows `sge` on 105 tracked keywords. So AI
Overview detection is effectively blind and `expected_ctr_at(..., ai_overview=…)`
uses the non-AIO curve almost everywhere, inflating expected clicks on every
SERP that carries one. The earned data undercounts — it only knows SERPs the
client appears in — but 105 beats 6.
