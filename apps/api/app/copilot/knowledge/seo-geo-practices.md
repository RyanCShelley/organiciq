# SEO and GEO practices from published guidance

Summaries in our own words of what Ahrefs and HubSpot publish, gathered
2026-10-15. These are vendor sources: much of the evidence is correlational and
some of it sells their tools. State findings as "Ahrefs reports" or "HubSpot
recommends", never as settled fact. Where this file and the Organic IQ process
disagree, the process wins. Review and extend this file by hand; the copilot
only reads it.

Sources:
- Ahrefs, How to Rank in AI Overviews: https://ahrefs.com/blog/how-to-rank-in-ai-overviews/
- Ahrefs, AI Overview brand visibility factors (75K brands): https://ahrefs.com/blog/ai-overview-brand-correlation/
- HubSpot, AEO best practices: https://blog.hubspot.com/marketing/answer-engine-optimization-best-practices

## Rank first, then answer directly

Ahrefs found most pages cited in AI Overviews also rank in the traditional top
10 (76% of 1.9M citations, median position 2), so classic ranking work remains
the base layer. Pages that answer the question directly and early are easier
for a model to use. HubSpot recommends opening each key section with a direct
answer of about 40 to 60 words, then supporting detail. This is the basis of
action V-2.

## Match intent and cover the sub-questions

AI Overviews appear most for informational, question-style queries, especially
long ones (seven or more words) and "why" questions. Match the dominant intent
of the results page. Ahrefs reports that pages ranking for the related
sub-queries an AI system fans out into were far more likely to be cited (161%
more likely, correlation 0.77), so cover the cluster of related questions
rather than one keyword. Build topical authority with clusters and internal
links (action V-4).

## Structure for extraction

HubSpot recommends bullets, numbered steps, tables and reusable blocks such as
definitions, pros and cons, and comparison tables, so answers can be lifted
cleanly. Mirror the question wording in an H2 or H3 and put the answer near the
top. Match the format the search results already show for featured snippets
(list or paragraph). This is the basis of action V-5.

## Schema markup

HubSpot recommends FAQPage for question-and-answer pairs, HowTo for
instructions, Article (headline, date, author, organization) for freshness and
authority signals, Organization site-wide for brand identity, and templates so
schema is applied across post types instead of page by page. Ahrefs treats
schema as a low-risk step that may help machine readability but says its direct
effect on citations is unproven. Schema and key content must be in the raw HTML:
markup injected by client-side JavaScript may not be read by AI crawlers. This
is the basis of actions V-2 and V-3.

## Off-site mentions matter more than backlinks for AI visibility

In Ahrefs' study of 75,000 brands, brand web mentions had the strongest
correlation with AI Overview brand visibility (0.664), well above backlinks
(0.218); branded anchors (0.527) and branded search volume (0.392) followed.
Brands in the top quartile for mentions averaged about 169 AI Overview mentions
against 14 for the next quartile. These are correlations from a sample of
domains with DR above 40, not proof of cause. Ahrefs' practical advice: earn
mentions on third-party sites, especially "best of" lists, reviews and
roundups, and on pages that are themselves heavily linked (correlation 0.70).
YouTube showed the strongest correlation (0.74) and is among the most-cited
domains. The relationship is much weaker for ChatGPT and Perplexity than for
Google AI Overviews, so do not assume the same lever works everywhere.

## What does not seem to matter

Ahrefs found word count nearly uncorrelated with AI citations; long pages see
diminishing returns past roughly 2,000 words. Adding loosely related content
to hedge can dilute intent. Stuffing keywords does not help. Over-focusing on
single keywords or single citations is a mistake; think in topics and
entities.

## Credibility and freshness

HubSpot recommends citations, statistics, expert quotes and original research,
and updating strong existing pages with new data on a regular cycle instead of
publishing new pages for every question. Check People Also Ask quarterly and
refresh pages that already perform. This supports the retainer refresh pool
(Content Opp).

## Local, voice and technical basics

HubSpot also recommends: a complete Google Business Profile (categories, hours,
photos, a response to every review), a landing page per service area with
consistent name, address and phone everywhere; plain, spoken-style answers for
voice queries; server-rendered critical content, semantic HTML, one H1 and a
logical heading order; Core Web Vitals within Google's thresholds (LCP under
2.5 seconds, CLS under 0.1); descriptive URLs and specific internal-link anchor
text.

## Measuring AI visibility

Both vendors say AI visibility is ongoing work, not a one-off project. Track
brand mentions and citations across AI platforms (by hand if there is no tool),
watch snippet and People Also Ask visibility in Search Console, watch branded
search and referral traffic in GA4, and ask new customers how they found you,
including AI tools. HubSpot suggests expecting early signs in about 4 to 8
weeks and business impact over 6 to 12 months. Ahrefs notes citations change
with each refresh, so judge trends, not single readings. AI Overviews rarely
link to the brand they mention (Ahrefs measured a link about 11% of the time
for its own brand), so mentions without clicks are normal.
