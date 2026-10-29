# OrganicIQ action catalog for launch

Prepared October 17, 2026. Companion to `REWORK-REVIEW.md`. Application code and source documents are unchanged.

## The compromise

Use the original playbook's bounded, executable jobs as the action model. Use the current engine's checks as findings that support those jobs. Let the account lead choose the constraint and approve the work against the client's strategy.

The playbook already includes human reprioritization, capacity limits, concrete completion criteria, tracking verification and explicit uncertainty. Preserve those principles. Change its “data decides” premise to “evidence informs the recommendation; the account lead decides.” Preserve broad account awareness without making every channel or every proposed integration a prerequisite for an organic action.

The source playbook's client examples are useful motivation, but their outcome claims were not independently validated here. No catalog can establish in advance that a particular action will produce growth. The launch standard should be a justified opportunity, an executable intervention and an honest outcome check.

Sources reviewed: `NOTES on actions.xlsx`, Sheet1 A1:E15, and the complete text and comment in the original Part 2 playbook. Document instructions are reference material, not authorization to change campaigns, contact clients, publish pages or create tasks.

## Six action types to ship

These are selectable jobs. Visibility, Traffic and Leads remain diagnostic lenses and outcome categories, rather than separate catalogs that prescribe the same job twice.

| Action | When it belongs in the proposal | What the brief must specify | Completion and outcome |
| --- | --- | --- | --- |
| **Improve or recover a priority page** | A selected keyword or topic has lost ground, the page misses confirmed intent, or CTR/engagement evidence justifies reviewing it. | Target page and intent, affected terms, observed issue, selected intervention and exact sections or snippet to change. Use a focused change or explicitly scoped deep refresh. | Approved changes live and annotated. Check matched keyword positions, relevant clicks and engagement according to the intervention. CTR is assessed in context of position and query mix. |
| **Improve AI answers and citations** | Selected prompts reveal a missing or lost citation, incorrect representation, or a specific answer gap the page can address. | Prompt set, engines and run dates, observed answers/citations, target page, concrete content format and supporting facts. Citation recovery is a variant. | Revised source is live and the same prompt set is checked again. Measure brand mentions, domain citations and target-page citations separately. |
| **Strengthen internal links** | A strategic page has weak relevant support and credible source pages exist. | Named source and target URLs, existing placement, proposed anchor and location, relevance rationale, duplicate-link checks. | Selected links live and verified by a crawl. Watch the target's relevant rankings and traffic; link installation alone is not evidence of lift. |
| **Improve conversion path** | A page has relevant demand and a reviewed mismatch in its offer, ask or onward route. | Audience intent, page evidence, intended next step, selected offer, exact CTA/link/proof change and measurement available. | Change live, destination works, relevant events tested. Use true landing-session conversions only when available; otherwise label page events or next-step clicks accurately. |
| **Add or repair relevant structured data** | Inspection verifies absent, incorrect or broken markup that has a defined purpose for this page/entity. | Exact types/properties, real entity identities and relationships, visible supporting content, existing graph to modify and validation method. | Valid, consistent markup deployed. Record technical completion separately from rankings or citation changes. Do not promise either from markup alone. |
| **Investigate a material change** | Important evidence lacks a defensible explanation, or a strategic competitor/cluster question needs a decision. | Question, scope, sources, time budget and required decision or follow-up. Competitor analysis and cluster planning are variants. | Evidence and conclusion recorded, with a counter-plan or a specific watch trigger if unresolved. Implementation work goes into approved future capacity. |

For launch, provide suggested check dates that the lead can edit. Use shipment as the start point, allow for indexing and source latency, and keep outcome status “insufficient evidence” when the sample cannot support a conclusion. Avoid one universal percentage or elapsed-time rule across all six jobs.

## Disposition of every current growth action

| Current action | Launch decision | How it changes |
| --- | --- | --- |
| V-6 Settle page ownership | Move to setup/review work | Confirm target ownership without spending a growth slot. If investigation proves a consolidation or redirect is needed, propose that implementation separately. |
| V-1 Put term in title/heading | Merge into priority-page improvement | Exact phrase absence is a review cue. Select a change only when it improves confirmed intent; preserve natural phrasing and explicit primary ownership. |
| V-8 Give secondary term a section | Keep inside page or AI-answer work | Name the missing subtopic, reader question, proposed heading and content. Do not add a section merely to repeat a synonym already answered. |
| V-2 Add answer block | Keep inside page or AI-answer work | Inspect existing content beyond FAQ entries. State the question and the answer that is missing. |
| V-7 Mark up FAQ | Keep conditionally within structured data | Confirm actual visible Q&A, applicable vocabulary and a defined purpose. No automatic growth recommendation from an FAQ heading alone. |
| V-5 Add something liftable | Merge into AI-answer work | Choose one justified format and specify its content. Plain prose can be a valid direct answer; a table/list is not inherently necessary. |
| V-3 Add entity markup | Keep within structured data | Inspect the existing graph and name actual entities/properties. Missing `about`/`mentions` alone is not a complete diagnosis. |
| V-4 Add internal links | Keep as a full action | Select relevant donors and placements. Being below the site median is a cue, not the reason the links matter. |
| T-1 Rewrite title/meta | Merge with V-1 into priority-page improvement | Select a snippet experiment after query/position/SERP review; avoid prescribing from the benchmark gap alone. |
| T-2 Match SERP format | Merge with V-5 into page or AI-answer work | One job may support both traffic and visibility. Confirm what format or source is actually relevant instead of promising to win a feature. |
| T-3 Rewrite opening | Keep inside priority-page improvement | Low engagement triggers inspection. Name the mismatch and proposed opening change before making it a task. |
| L-1 Add onward route | Merge into conversion-path improvement | Show detected links and reviewed missing destination; do not claim measured visitor abandonment. |
| L-2 Add CTA | Merge into conversion-path improvement | Show what the crawler detected and allow confirmation/correction. Identify the actual ask and destination. |
| L-3 Match offer to stage | Merge into conversion-path improvement | Present the confirmed stage and compatible offers as a rule-based suggestion, with the reasoning visible. |

## What the conversion actions actually know

### L-1 uses a crawl graph

`apps/api/app/ingestion/crawler/parse.py:563` extracts same-site HTML links. Links inside `nav`, `header`, `footer`, `menu` or `aside` are treated as outside editorial content. The crawler also marks a destination as template-linked when at least half of crawled pages link to it in content, once the crawl has at least ten pages (`fetch.py:735`). This is a heuristic: a genuinely useful conversion destination can be excluded because it is common.

`services/page_signals.py:431` compares the remaining links with declared conversion-page URLs. It attaches the destination's declared stage. L-1 proposes a route when a confirmed non-bottom-funnel page has no such route and a compatible offer exists.

That is real structural evidence, but not a record of user journeys. It can miss links outside its extraction rules, stale or failed crawl data, and destinations not declared as conversion pages. Show source URL, destination, anchor, content/template classification and crawl date. Say “no qualifying link detected in this crawl” until someone verifies the page.

### L-2 uses a broad element counter

`parse.py:608` sums HTML forms, `tel:` and `mailto:` links, and anchors/buttons/submit inputs whose text matches patterns such as contact, call, book, schedule, request, quote, trial, subscribe, buy or order. These counts include navigation and footer elements. An element may contribute more than once, and a form is counted whether or not it is a lead form. A successful 2xx fetch is required to store the count; otherwise the pipeline stores unknown (`pipeline.py:150`).

This is neither unique CTA inventory nor click/conversion tracking. It does not establish prominence, usability, intent fit or successful event firing. “Get the guide” or an embedded third-party experience can be missed. A footer phone link can suppress a missing-CTA finding even when the page's main content has no useful ask.

For launch, label it “possible conversion elements detected,” expose the extraction evidence where available and require page review. Better element inventory is a follow-up: text, type, URL/action, location, render/capture status and event mapping. Do not hold the whole catalog for that enhancement.

### L-3 uses confirmed stages and a compatibility table

`services/page_stage.py` proposes funnel stages from page content, but the engine reads only confirmed stages. `decisions/catalog.py:729` defines allowed next-step stages: early learning can go to early/comparison offers, comparison can go to comparison/buying offers, and buying can go to buying offers. Offers with no stage are treated as generic matches. Eligible offers are sorted by URL in `services/page_signals.py:527`, not by measured conversion performance.

The engine therefore knows that a link conflicts with its stage rules; it does not know whether a visitor is ready, whether the offer persuades, or which offer performs best. Replace “the reader is not ready” with the actual rule and ask the lead to choose the offer. Behavioral validation can use manually reviewed analytics/journeys now; no Swetrix integration was found in the current application code.

## Relationship to the original twelve SOPs

| Original SOP | Launch treatment |
| --- | --- |
| 1 Tracking Repair | Keep as an incident/measurement-repair workflow. Confirm the failure by a live test. Mark affected dates and metrics. It can preempt scheduled work, with the capacity consequence explicit, rather than silently adding a growth slot. |
| 2 Conversion-Page Improvement | Conversion-path action. Journey review may be supplied manually while integrations are incomplete. |
| 3 Money-Term Rescue | Priority-page action, with diagnosis before choosing the intervention. |
| 4 Deep Refresh | Scoped priority-page variant. Keep routine refresh allowances distinct; a large rebuild becomes a project. |
| 5 GEO / Dual-Optimization | AI-answer action, grounded in actual prompt observations. |
| 6 Citation Recovery | AI-answer variant with a recorded previous citation or factual-error observation. |
| 7 Campaign Action | Manual specialist recommendation for launch; no autonomous spend or campaign changes. Execution depends on account ownership and explicit approval. |
| 8 Paid Landing Alignment | Manually selected conversion/page variant with supplied ad-to-landing evidence. Defer automatic recommendations until campaign data is sufficient. |
| 9 Channel Investigation | Investigation action. Preserve managed versus observed channel ownership. |
| 10 Internal-Link Architecture | Dedicated internal-link action. The proposed 5–10 donors is a working range, not a quota to fill with irrelevant links. |
| 11 Cluster Completion | Investigation/planning variant. New pieces consume future content allowance; avoid counting their writing twice. |
| 12 Competitor Visibility | Investigation variant with a bounded counter-plan. |

Create-a-page work remains in the existing new-content allowance. Its evidence can come from a confirmed prompt intent as well as a keyword; lack of keyword volume must not erase it. Preserve contractual growth/update/content limits in one reviewed plan view. The old playbook says Scale while the current application uses Lift; use the client's stored agreement and resolved allowances rather than silently adopting the old labels.

Keep page-target mapping and routine setup corrections outside growth capacity. A substantial research or implementation job discovered during setup can be separately scoped. Do not let minor checks consume a month's only growth action.

## Make the AI brief concrete

“Add something liftable” is not sufficient. Neither is choosing a table simply because a feature exists.

A proposal must name the target prompt/question, target section, chosen format, required facts and sources, and what current answers or cited pages suggest. The format can be a direct answer paragraph, comparison table, steps or definition. A specialist confirms that it fits the intent.

For example, if reviewed prompts ask for a material comparison and current cited sources answer it with comparable specifications, the brief could request a table with rows for the actual products/materials and columns for the relevant specifications, units and sources. Values must come from verified product evidence. The engine must not invent values, competitors or comparative claims. If the sources or comparison are missing, propose investigation first.

Both V-5 and T-2 should contribute evidence to that same brief. Record secondary outcomes without duplicating the job into Visibility and Traffic slots. Also correct V-5's measurement contract: its current label promises position and AI citations while its `metric_key` measures only term position.

## Structured data and current search behavior

Retain a structured-data action because the user explicitly values this work. Require a defined purpose and truthful, applicable markup. Google says structured data should represent visible page content, and valid markup does not guarantee a search feature. [Google structured-data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies).

One material update: Google's documentation records the end of FAQ rich results on May 7, 2026 and removal of the feature documentation on June 15. Do not justify FAQ markup by promising an FAQ rich result. This does not establish that FAQ vocabulary has no other use. [Google documentation updates](https://developers.google.com/search/updates).

Google also states that its AI features require no special schema.org markup. That guidance concerns Google Search; it is not proof about every LLM provider. Keep entity/schema work where it clarifies real content or fixes defects, but treat citation improvement as an outcome to test. [Google AI features guidance](https://developers.google.com/search/docs/appearance/ai-features).

## Minimum build to launch

1. Produce six editable brief types and map existing rule findings to them. Preserve legacy IDs for history. Collect related findings instead of stopping at the first matching rule.
2. Add a visible evidence panel and the missing human controls: select focus, choose an intervention, edit brief, choose offer, confirm uncertain crawl findings, add manual work, approve the plan. Keep target setup outside growth capacity.
3. Include all selected keywords and prompts with existing-page/planned-page/unmapped/excluded states. Allow prompt observations to be supplied through a validated import or manual evidence record initially, preserving provider, dates and actual results.
4. Keep automatic candidates within demonstrated data support. Offer manual workflows for paid, journey review, cluster and competitor work without pretending the integrations exist.
5. Save the approved plan version, capacity allocation, rationale and exact baseline. Start outcome checks from shipment and iterate the effective approved plan.

Before rollout, run each proposed brief on representative client cases. The lead should be able to see why it matters, verify the evidence, understand the task and explain how the outcome will be checked. Reject or revise briefs that fail that review. Passing parser or threshold tests does not establish business impact.

The playbook comment requesting major US holidays belongs in comparison context: configurable holiday annotations plus client-specific seasonality, YoY where history is valid, and an explicit fallback when it is not. A holiday marker should not automatically explain away a decline. Build a minimal comparison selector now; a complete holiday/calendar system should not delay the action workflow.
