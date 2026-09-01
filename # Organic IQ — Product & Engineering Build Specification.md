\# Organic IQ — Product & Engineering Build Specification

\*\*Version:\*\* 1.0    
\*\*Status:\*\* Greenfield Build    
\*\*Product:\*\* Organic IQ    
\*\*Company:\*\* SMA Marketing

\---

\# 1\. Product Vision

Organic IQ is SMA Marketing's operating system for predictable organic growth.

It combines:

\- Search performance  
\- AI search visibility  
\- Website traffic  
\- Lead/conversion performance  
\- Competitive visibility  
\- Client strategy  
\- Decision intelligence  
\- Growth actions  
\- Performance annotations

into one connected system.

Organic IQ is NOT simply an SEO dashboard.

The system should help SMA answer:

1\. Are we generating business conversion?  
2\. Is the client's visibility increasing?  
3\. Is that visibility producing traffic?  
4\. Where is growth being constrained?  
5\. What should SMA do next?  
6\. Did the action we took improve performance?

The core operating loop is:

Strategy  
→ Measure  
→ Diagnose  
→ Recommend  
→ Execute  
→ Annotate  
→ Measure Again

The application should be built around this loop.

\---

\# 2\. Core Product Principle

Organic IQ measures organic growth through three layers:

CONVERSION  
↓  
VISIBILITY  
↓  
TRAFFIC

The Decision Engine analyzes the relationships between these layers and recommends Growth Actions.

The application must use one normalized data layer for:

\- Dashboard reporting  
\- Watchlists  
\- Decision Engine  
\- Growth Actions  
\- Annotations  
\- Future reporting

Do not build separate reporting and decision-engine pipelines.

\---

\# 3\. Technology Stack

Build Organic IQ as a modern web application.

Preferred stack:

\#\# Frontend

\- Next.js  
\- TypeScript  
\- Tailwind CSS  
\- Appropriate charting library

\#\# Backend

\- Python / FastAPI

Python should handle:

\- External API ingestion  
\- Data normalization  
\- Metric calculations  
\- Decision Engine  
\- Scheduled jobs  
\- Analytics logic

\#\# Database

PostgreSQL

\#\# Hosting

Railway is acceptable for:

\- PostgreSQL  
\- FastAPI  
\- Worker/jobs

Frontend may use Railway or Vercel.

\#\# Authentication

Implement authentication in a way that supports:

\- SMA Admin  
\- SMA Team  
\- Client Admin  
\- Client Viewer

Client-facing authentication does NOT need to be implemented in the first build milestone, but the data model must support it.

\---

\# 4\. Multi-Client Architecture

Organic IQ is multi-client from the beginning.

\`client\_id\` is a foundational key.

Every client-owned record must contain or resolve to:

client\_id

This includes:

\- integrations  
\- metrics  
\- keywords  
\- prompts  
\- competitors  
\- topics  
\- pages  
\- goals  
\- decisions  
\- tasks  
\- annotations  
\- content plans

Never rely on UI filtering alone for client isolation.

Client scoping must occur in backend queries and data access.

\---

\# 5\. Primary Application Navigation

The initial application should contain:

1\. Dashboard  
2\. Watch List  
3\. Decision Engine  
4\. Activity  
5\. Client Strategy  
6\. Admin

Do not add unnecessary navigation during the initial build.

\---

\# 6\. Global Application Context

For internal SMA users, provide global controls for:

\#\# Client

A client selector should establish the active client throughout the application.

Changing the client updates all client-scoped views.

\#\# Date Range

Support:

\- Last 7 days  
\- Last 14 days   
\- Last 30 days  
\- Last 90 days  
\- Last 6 months  
\- Last 12 months  
\- Custom

Default:

Last 90 days

Where useful, metrics should compare against the immediately preceding equivalent period.

Example:

Current:  
Jun 1 – Aug 29

Previous:  
Mar 3 – May 31

\---

\# 7\. Client Record

Each client has one master account record.

Suggested fields:

client\_id  
client\_name  
domain  
OrgnaicIQ tier  
start\_date  
primary\_market  
timezone  
monthly\_lead\_goal  
created\_at  
updated\_at

Possible status values:

active  
paused  
onboarding  
archived

\---

\# 8\. Client Strategy

Organic IQ should eventually replace the external account-record spreadsheet as the primary strategy record.

Each client should support:

\#\# Goals

\- Monthly lead target  
\- Primary conversion  
\- Secondary conversions  
\- Organic growth objectives  
	Visiblity, traffic, ect

\#\# Business Context

\- Core services/products  
\- Target markets  
\- Target locations  
\- Primary audiences  
\- Competitors

\#\# Organic Strategy

\- Priority topics  
\- Search priorities  
\- AI visibility priorities  
\- Conversion priorities

This data should eventually help provide context to the Decision Engine.

\---

\# 9\. Client Tier

Each client must have an Organic IQ tier.

Do not hard-code tier behavior throughout the application.

Create configurable tier records.

Example:

tier\_id  
tier\_name  
tracked\_keyword\_limit  
tracked\_prompt\_limit  
content\_allowance  
update\_allowance  
conversion\_limit  
reporting\_level

The application should eventually use tier configuration to determine available services and expected work.

\---

\# 10\. Integrations

Each client may connect:

\- Google Analytics 4  
\- Google Search Console  
\- SE Ranking

The integration system must store:

client\_id  
provider  
external\_account\_id  
external\_property\_id  
connection\_status  
last\_sync\_started  
last\_sync\_completed  
last\_successful\_sync  
last\_fact\_date  
error\_message

Credentials/tokens must be stored securely.

Never expose secrets in the frontend.

\---

\# 11\. Google OAuth

GA4 and Google Search Console should use OAuth.

Admin workflow:

Client  
→ Integrations  
→ Connect Google  
→ OAuth  
→ Select GA4 Property  
→ Select GSC Property  
→ Save

Connection status should be visible.

Example:

GA4  
Connected  
Property: 123456  
Last Sync: Aug 31, 8:42 AM

GSC  
Connected  
Property: https://example.com/  
Last Sync: Aug 31, 8:45 AM

\---

\# 12\. SE Ranking Integration

Each client maps to an SE Ranking project.

Store:

client\_id  
se\_ranking\_project\_id  
project\_name

SE Ranking should be the primary tracking source for:

\#\# Search

\- tracked keywords  
\- keyword rankings  
\- search volume  
\- groups/tags  
\- competitors  
\- competitor rankings  
\- visibility  
\- Share of Voice where available

\#\# AI

\- tracked prompts  
\- AI engines  
\- brand mentions  
\- citations  
\- competitor mentions  
\- competitor citations  
\- AI visibility  
\- AI Share of Voice where available

\#\# Technical

Use SE Ranking Website Audit data where useful and available.

Do not create fake values when an SE Ranking metric is unavailable.

\---

\# 13\. Data Pipeline Architecture

All external sources follow the same ingestion philosophy:

SOURCE API  
↓  
STAGING  
↓  
NORMALIZATION  
↓  
FACTS  
↓  
VALIDATION  
↓  
PUBLISH

The Dashboard and Decision Engine only consume validated normalized data.

They must NOT read directly from:

\- external APIs  
\- staging tables

\---

\# 14\. Sync Jobs

Every ingestion request creates a durable job.

Suggested job record:

job\_id  
client\_id  
source  
start\_date  
end\_date  
status  
started\_at  
completed\_at  
records\_fetched  
records\_written  
fact\_watermark  
validation\_status  
error\_message

Statuses:

queued  
fetching  
staging  
normalizing  
validating  
successful  
partial  
failed

Do not use process-local background tasks as the sole mechanism for critical ingestion.

Jobs must survive:

\- web request completion  
\- application restart  
\- deployment

\---

\# 15\. Success Contract

A data sync is successful only when:

1\. API fetch succeeds.  
2\. Requested reporting window is retrieved.  
3\. Staging write succeeds.  
4\. Normalization succeeds.  
5\. Fact tables update.  
6\. Validation passes.  
7\. Fact watermark reaches expected end date.

Never report success before this sequence completes.

\---

\# 16\. Data Health

Create an Admin Data Health view.

Example:

| Source | Status | Fact Through | Last Sync | Validation |  
|---|---|---|---|---|  
| GA4 | Healthy | Aug 30 | 8:42 AM | Passed |  
| GSC Pages | Healthy | Aug 30 | 8:45 AM | Passed |  
| GSC Queries | Healthy | Aug 30 | 8:45 AM | Passed |  
| SE Ranking | Healthy | Aug 31 | 8:47 AM | Passed |

Possible states:

Healthy  
Stale  
Syncing  
Partial  
Failed  
Not Connected

Never silently display stale data as current.

\---

\# 17\. Google Analytics Data Model

GA4 powers:

\- CONVERSION  
\- Website traffic  
\- Channel performance  
\- Landing-page performance

Required dimensions should include where supported:

client\_id  
date  
landing\_page  
session\_source  
session\_medium  
channel  
event\_name

Required metrics should include:

sessions  
active\_users  
views  
Sessionc to Key\_event rate  
key\_events

\---

\# 18\. Organic IQ Channel Classification

Do not rely exclusively on GA4 default channel grouping.

Organic IQ should maintain its own normalized channel classification.

Initial channels:

Organic Search  
AI Referral  
Direct / Unattributed  
Paid Search  
Referral  
Social  
Email  
Other

Maintain configurable source rules.

Example AI sources may include:

chatgpt  
perplexity  
gemini  
claude  
copilot

Do not automatically classify Direct as Organic.

Direct / Unattributed remains distinct.

\---

\# 19\. Lead Definition

Each client must define what constitutes a lead.

Create configurable conversion definitions.

Example:

conversion\_definition\_id  
client\_id  
event\_name  
conversion\_name  
conversion\_type  
is\_primary  
active

Examples:

generate\_lead  
form\_submit  
phone\_call  
book\_appointment  
request\_quote

Do not globally assume every GA4 key event is a business lead.

\---

\# 20.CONVERSION Metrics

Primary dashboard CONVERSION KPIs:

\#\# Leads

Count of configured lead events.

\#\# Lead Rate

Leads / relevant sessions

\#\# Leads by Channel

Breakdown across Organic IQ channel classification.

Potential future metrics:

\- Monthly Lead Goal  
\- Goal Progress  
\- Managed Lead Share  
\- Revenue  
\- Qualified Leads

\---

\# 21\. Google Search Console Data

GSC must maintain separate page and query/page fact datasets.

Do not attempt to make one grain serve every report.

\---

\# 22\. GSC Page Facts

Suggested grain:

client\_id  
date  
page  
country  
device

Metrics:

impressions  
clicks  
ctr  
average\_position

Used for:

\- Dashboard  
\- Page performance  
\- Search traffic trends  
\- CTR opportunities  
\- Decision Engine

\---

\# 23\. GSC Query/Page Facts

Suggested grain:

client\_id  
date  
query  
page  
country  
device

Metrics:

impressions  
clicks  
ctr  
average\_position

Used for:

\- Top Queries  
\- Search opportunities  
\- SERP analysis  
\- Query/page relationships  
\- Topic mapping  
\- Decision Engine

Never represent page-only rows as query records with blank query values.

\---

\# 24\. Search Watch List

The Search Watch List comes primarily from SE Ranking.

Each record should support:

client\_id  
keyword  
keyword\_group  
search\_volume  
current\_position  
previous\_position  
ranking\_change  
search\_visibility  
topic\_id  
intent  
priority

Where available:

competitor rankings  
Search SOV

Organic IQ may enrich SE Ranking records with internal strategic metadata.

\---

\# 25\. AI Prompt Watch List

AI Prompt Watch List comes primarily from SE Ranking.

Suggested fields:

client\_id  
prompt  
engine  
topic\_id  
intent  
brand\_mentioned  
brand\_cited  
citation\_url  
competitors\_mentioned  
competitors\_cited  
ai\_visibility  
ai\_sov  
checked\_at

The UI should allow filtering by:

\- Topic  
\- AI engine  
\- Mention status  
\- Citation status  
\- Visibility

\---

\# 26\. Topics

Topics provide the common strategic layer connecting multiple datasets.

Create:

topics

Suggested fields:

topic\_id  
client\_id  
topic\_name  
description  
priority  
status

Eventually relate topics to:

\- pages  
\- keywords  
\- prompts  
\- conversions  
\- decisions  
\- annotations

The long-term model is:

CLIENT  
↓  
TOPIC  
↓  
PAGE  
↓  
QUERY / KEYWORD / PROMPT  
↓  
TRAFFIC  
↓  
LEAD

Do not require all topic relationships for the first milestone.

Design for them now.

\---

\# 27\. Dashboard

The Dashboard is the primary client performance view.

It must remain simple.

Structure:

Conversions  
↓  
VISIBILITY  
↓  
TRAFFIC

\---

\# 28\. Dashboard — Conversions

Display:

\#\# Leads

Current period  
Previous period  
% change

\#\# Lead Rate

Current period  
Previous period  
Change

\#\# Leads by Channel

Show breakdown for:

Organic Search  
AI Referral  
Direct / Unattributed  
Paid where applicable  
Other

Where configured, display:

Monthly Lead Goal  
Progress toward Goal

\---

\# 29\. Dashboard — Visibility

Separate Search and AI visibility.

\#\# Search Visibility

Display:

\- Search Visibility  
\- Search SOV  
\- GSC Impressions  
\- Average Position

Supporting views:

\- Visibility trend  
\- Keyword distribution  
\- Competitor comparison  
\- Top gaining/losing terms

\#\# AI Visibility

Display:

\- AI Visibility  
\- AI SOV

Supporting views:

\- AI engine breakdown  
\- Prompt coverage  
\- Competitor comparison  
\- Brand citations  
\- Top gaining/losing prompts

Do NOT create a combined arbitrary Organic IQ Visibility Score initially.

\---

\# 30\. Dashboard — Traffic

Display:

\- GSC Clicks  
\- GSC CTR  
\- GA4 Sessions  
\- GA4 Views

Supporting views:

\#\# Traffic by Channel

Organic Search  
AI Referral  
Direct  
Paid  
Referral  
Social  
Other

\#\# Top Pages

Show:

page  
GSC impressions  
GSC clicks  
CTR  
average position  
GA4 sessions  
views  
leads  
lead rate

Do not force cross-source joins until URLs are normalized reliably.

\---

\# 31\. URL Normalization

Create a canonical URL normalization strategy.

Handle:

\- protocol  
\- www/non-www  
\- trailing slash  
\- query parameters  
\- fragments  
\- case where relevant

Maintain both:

raw\_url  
normalized\_url

Cross-source page joins should use normalized URLs.

Do not destroy original source URLs.

\---

\# 32\. Watch List UI

Create two primary tabs:

\#\# Search

Display:

Keyword  
Topic  
Volume  
Position  
Change  
Visibility  
Search SOV where appropriate

\#\# AI

Display:

Prompt  
Topic  
Engine  
Mentioned  
Cited  
AI Visibility  
AI SOV

Allow:

\- filtering  
\- sorting  
\- date comparison  
\- topic filtering

\---

\# 33\. Search Console Opportunities

Create an opportunity view using GSC query/page data.

Initial opportunity types may include:

\#\# High Impression / Low CTR

Visible but failing to capture expected traffic.

\#\# Striking Distance

Meaningful impressions/volume with positions approximately 8–20.

\#\# Declining Query/Page

Material deterioration versus previous period.

\#\# Cannibalization Candidate

Multiple pages competing for the same meaningful query/topic.

Do not hard-code final thresholds globally.

Create configurable rule parameters.

\---

\# 34\. Decision Engine Purpose

The Decision Engine answers:

\> Based on current validated performance data, what should SMA investigate or do next?

The Decision Engine does NOT replace human judgment.

It identifies:

\- bottleneck  
\- evidence  
\- opportunity  
\- recommended Growth Action  
\- priority  
\- success metric

\---

\# 35\. Decision Engine Diagnostic Order

Analyze performance in this conceptual sequence:

VISIBILITY  
↓  
TRAFFIC  
↓  
CONVERSION

The engine should identify where performance is being constrained.

\---

\# 36\. Five Growth Actions

Every performance-triggered recommendation must map to one of five Growth Actions.

\---

\#\# Growth Action 1  
\# Internal Linking & Site Architecture

Purpose:

Improve authority distribution and discoverability of priority pages.

Signals may include:

\- valuable page ranking outside strongest positions  
\- weak internal support  
\- orphan pages  
\- topic architecture problems  
\- competing pages

Possible actions:

\- add internal links  
\- improve anchors  
\- fix orphan pages  
\- improve navigation  
\- strengthen topical relationships

\---

\#\# Growth Action 2  
\# Technical SEO & Indexation

Purpose:

Remove technical barriers suppressing performance.

Signals may include:

\- indexation issues  
\- canonical problems  
\- broken links  
\- redirects  
\- sitemap problems  
\- crawl issues  
\- rendering problems  
\- Core Web Vitals

Potential source:

SE Ranking Website Audit and other validated technical data.

\---

\#\# Growth Action 3  
\# SERP & CTR Optimization

Purpose:

Convert existing visibility into additional search traffic.

Signals may include:

\- high impressions  
\- strong average position  
\- below-expected CTR  
\- declining CTR  
\- cannibalization  
\- SERP feature opportunity

Possible actions:

\- optimize title  
\- optimize meta description  
\- improve SERP intent alignment  
\- address cannibalization  
\- improve rich-result eligibility

\---

\#\# Growth Action 4  
\# Structured Data, Entities & AI Visibility

Purpose:

Improve machine understanding and visibility across search and AI systems.

Signals may include:

\- low AI visibility relative to search visibility  
\- low AI SOV  
\- competitor citation advantage  
\- missing structured data  
\- entity ambiguity  
\- citation opportunities

Possible actions:

\- implement/fix schema  
\- strengthen entity relationships  
\- improve organization/service/product data  
\- improve AI citation eligibility  
\- address AI visibility gaps

\---

\#\# Growth Action 5  
\# Conversion Path Optimization

Purpose:

Turn existing traffic into more business outcomes.

Signals may include:

\- traffic increasing while leads remain flat  
\- declining lead rate  
\- high-traffic page with poor conversion  
\- weak informational → commercial path

Possible actions:

\- improve CTA  
\- improve forms  
\- improve phone path  
\- add trust signals  
\- improve conversion-page navigation  
\- improve landing-page intent alignment

\---

\# 37\. Content Planning Signals

Content is NOT one of the five Decision Engine Growth Actions.

Content creation and routine optimization are handled through SMA's monthly SOP.

The Decision Engine may create:

CONTENT PLANNING SIGNAL

Examples:

\- missing topic coverage  
\- meaningful demand with no suitable page  
\- intent gap  
\- weak supporting content  
\- competitor content advantage

These signals should feed the monthly content planning process.

\---

\# 38\. Decision Record

Every generated decision should be stored.

Suggested structure:

decision\_id  
client\_id  
created\_at  
decision\_type  
growth\_action  
priority  
status  
topic\_id  
page\_url  
query  
keyword  
prompt  
diagnosis  
recommended\_action  
evidence\_json  
baseline\_metrics\_json  
success\_metric  
date\_range\_start  
date\_range\_end

Do not only render decisions dynamically and discard them.

Preserve historical decisions.

\---

\# 39\. Decision Status

Suggested statuses:

New  
Reviewed  
Accepted  
Dismissed  
Task Created  
Completed  
Measuring  
Validated

Preserve dismissal reason when applicable.

\---

\# 40\. Growth Task Creation

When a user selects a Decision Engine output, allow:

Create Growth Task

Workflow:

Decision  
↓  
Generate Task  
↓  
Review/Edit  
↓  
Send to Teamwork  
↓  
Create Annotation

Do not automatically send recommendations to Teamwork without review.

\---

\# 41\. Growth Task

Suggested task model:

task\_id  
client\_id  
decision\_id  
growth\_action  
title  
description  
priority  
assigned\_to  
due\_date  
status  
teamwork\_task\_id  
teamwork\_task\_url  
created\_at  
completed\_at

Task titles should be specific.

Good:

Optimize SERP CTR — Carbon Fiber Tubes

Add Internal Links — UAV Applications

Improve Conversion Path — Request a Quote

Bad:

SEO Task

Fix SEO

Organic IQ Recommendation \#32

\---

\# 42\. Teamwork Boundary

Teamwork owns:

\- assignment  
\- due dates  
\- comments  
\- task execution  
\- checklists  
\- completion

Organic IQ owns:

\- why the task exists  
\- triggering evidence  
\- baseline  
\- recommendation  
\- growth category  
\- measurement  
\- result

Do not rebuild Teamwork inside Organic IQ.

\---

\# 43\. Annotations

Annotations create the historical record of meaningful changes.

Suggested fields:

annotation\_id  
client\_id  
decision\_id  
growth\_task\_id  
date  
annotation\_type  
growth\_action  
description  
topic\_id  
page\_url  
baseline\_metrics\_json  
success\_metric  
teamwork\_task\_id  
completed\_at  
measurement\_start\_date  
measurement\_end\_date  
post\_action\_metrics\_json  
result  
notes

\---

\# 44\. Annotation Types

Examples:

Growth Action  
Content Published  
Content Updated  
Technical Change  
Website Change  
Conversion Change  
Campaign Change  
Algorithm/Event  
Manual Note

Annotations should eventually appear on relevant trend charts.

\---

\# 45\. Closed-Loop Measurement

The long-term Organic IQ advantage is:

DETECT  
↓  
ACT  
↓  
MEASURE

For Growth Actions, preserve:

\- triggering metrics  
\- baseline  
\- completion date  
\- success metric  
\- measurement window  
\- post-action performance  
\- result

Suggested result values:

Improved  
No Meaningful Change  
Declined  
Not Enough Data  
Not Yet Measured

\---

\# 46\. Activity

Create an Activity view showing meaningful Organic IQ events.

Examples:

\- recommendation generated  
\- recommendation accepted  
\- Teamwork task created  
\- task completed  
\- annotation created  
\- content published  
\- integration synced  
\- measurement completed

This becomes the client's Organic IQ history.

\---

\# 47\. Content Plan

Organic IQ should eventually contain the client content plan.

Suggested fields:

content\_item\_id  
client\_id  
topic\_id  
title  
content\_type  
action\_type  
target\_url  
status  
planned\_date  
published\_date  
teamwork\_task\_id

Possible action types:

New  
Update  
Consolidate

This is not required for the initial reporting milestone.

Design database relationships so it can be added cleanly.

\---

\# 48\. Admin

Admin should contain:

\#\# Clients

Create/edit clients.

\#\# Integrations

Manage GA4, GSC and SE Ranking connections.

\#\# Data Health

View sync/freshness status.

\#\# Sync Jobs

Inspect job history and errors.

\#\# Configuration

Manage:

\- tiers  
\- conversion definitions  
\- channel rules  
\- decision thresholds  
\- AI source mappings

\---

\# 49\. Client Authentication — Future Phase

Design for:

SMA Admin  
SMA Team  
Client Admin  
Client Viewer

SMA users can select authorized clients.

Client users should automatically enter their own client context.

Do not expose internal configuration or decision controls unless role permits.

\---

\# 50\. Build Phases

Build Organic IQ incrementally.

Do not attempt the entire product in one implementation pass.

\---

\# PHASE 1 — Foundation

Build:

\- project structure  
\- PostgreSQL  
\- client model  
\- integration model  
\- sync job model  
\- authentication foundation  
\- client selector  
\- date context  
\- basic Admin

Acceptance:

Multiple clients can exist and are correctly isolated.

\---

\# PHASE 2 — GSC

Implement:

\- Google OAuth  
\- GSC property mapping  
\- GSC page ingestion  
\- GSC query/page ingestion  
\- staging  
\- facts  
\- validation  
\- freshness  
\- sync jobs

Test:

ONE CLIENT  
14 DAYS

Acceptance:

\- correct page totals  
\- real query records  
\- no blank-query substitution  
\- no overlapping jobs  
\- correct fact watermark  
\- explicit failures

Do not expand until this passes.

\---

\# PHASE 3 — GA4

Implement:

\- GA4 OAuth/property mapping  
\- traffic ingestion  
\- conversion ingestion  
\- channel normalization  
\- landing-page data  
\- facts  
\- validation

Test:

ONE CLIENT  
14 DAYS

Validate against GA4 source data.

\---

\# PHASE 4 — SE Ranking Search

Implement:

\- project mapping  
\- tracked keywords  
\- rankings  
\- volume  
\- groups  
\- competitors  
\- visibility  
\- available SOV data

Populate Search Watch List.

\---

\# PHASE 5 — SE Ranking AI

Implement:

\- prompts  
\- engines  
\- mentions  
\- citations  
\- competitors  
\- AI visibility  
\- available AI SOV

Populate AI Watch List.

\---

\# PHASE 6 — Dashboard

Build:

CONVERSION  
VISIBILITY  
TRAFFIC

Only use validated fact data.

Implement:

\- client filter  
\- date filter  
\- period comparisons  
\- data freshness indicators

Validate every KPI against its source.

\---

\# PHASE 7 — 90-Day Validation

Expand one test client to:

90 DAYS

Validate:

\- ingestion stability  
\- metric accuracy  
\- freshness  
\- performance  
\- period comparisons

Only after this succeeds begin broader client onboarding.

\---

\# PHASE 8 — Multi-Client

Onboard several clients.

Acceptance:

\- strict client isolation  
\- correct integrations  
\- correct project mappings  
\- stable sync jobs  
\- correct date filters

\---

\# PHASE 9 — Decision Engine

Only after reporting data is trusted:

\- implement decision rules  
\- build configurable thresholds  
\- store decisions  
\- map decisions to Growth Actions  
\- create Content Planning Signals  
\- add evidence  
\- add success metrics

Validate recommendations manually against SMA judgment.

\---

\# PHASE 10 — Growth Actions & Annotations

Implement:

Decision  
→ Growth Task  
→ Teamwork  
→ Annotation  
→ Measurement

\---

\# PHASE 11 — Strategy & Content Plan

Move relevant client account records into Organic IQ.

Implement:

\- goals  
\- strategy  
\- content plan  
\- competitor context  
\- priority topics

\---

\# PHASE 12 — Client Portal

Implement:

\- client authentication  
\- roles  
\- client-facing reporting  
\- approved activity/history  
\- strategy visibility where appropriate

\---

\# 51\. Initial Acceptance Definition

Do not consider Organic IQ operational until one client can:

1\. Connect GA4.  
2\. Connect GSC.  
3\. Map an SE Ranking project.  
4\. Complete reliable syncs.  
5\. Show correct CONVERSION  
6\. Show correct Search Visibility.  
7\. Show correct AI Visibility.  
8\. Show correct Traffic.  
9\. Show Search Watch List.  
10\. Show AI Watch List.  
11\. Filter consistently by date.  
12\. Preserve client isolation.  
13\. Explicitly show data freshness.  
14\. Run without overlapping/broken ingestion jobs.

Only then should Decision Engine automation become a priority.

\---

\# 52\. Engineering Rules

\#\# Rule 1 — Correctness First

Never prefer a visually complete dashboard over accurate data.

\#\# Rule 2 — No Fake Data

Do not substitute placeholder metrics in production views.

Unavailable means unavailable.

\#\# Rule 3 — One Fact Layer

Dashboard and Decision Engine use the same normalized data.

\#\# Rule 4 — Client Isolation

Every client-owned query must explicitly enforce client access.

\#\# Rule 5 — Durable Jobs

Critical ingestion must not depend solely on a web process remaining alive.

\#\# Rule 6 — Idempotent Ingestion

Running the same source/client/date sync twice should not create duplicate facts.

\#\# Rule 7 — Explicit Freshness

Always know how current the data is.

\#\# Rule 8 — Explicit Failure

Never convert partial failure into success.

\#\# Rule 9 — Preserve Raw Source Meaning

Normalize data without destroying source records required for debugging.

\#\# Rule 10 — Small Increments

Build and validate one source at a time.

\---

\# 53\. Instructions to Cursor

This is a GREENFIELD build.

Do not attempt to preserve architecture from previous Radar or Organic IQ prototypes unless explicitly instructed.

Old code may be referenced for:

\- API knowledge  
\- useful normalization logic  
\- validated calculations  
\- UI inspiration

but it is NOT the architectural foundation.

When implementing this specification:

1\. Read this entire document first.  
2\. Do not build the whole application at once.  
3\. Follow the build phases in order.  
4\. Before coding a phase, propose:  
   \- architecture  
   \- database changes  
   \- files/modules  
   \- dependencies  
   \- acceptance tests  
5\. Wait for approval before large architectural changes.  
6\. Prefer simple, maintainable patterns.  
7\. Do not create parallel data pipelines.  
8\. Do not couple reporting directly to external APIs.  
9\. Do not couple Decision Engine logic to UI components.  
10\. Do not couple Teamwork integration directly to Decision Engine rules.  
11\. Keep source ingestion, normalization, analytics, decision logic and UI separated.  
12\. Add automated tests for critical data behavior.  
13\. Treat data correctness as more important than feature velocity.  
14\. Keep implementation consistent with the Organic IQ operating loop:

Strategy  
→ Measure  
→ Diagnose  
→ Recommend  
→ Execute  
→ Annotate  
→ Measure Again

\---

\# 54\. First Cursor Task

After reading this specification:

DO NOT begin building the dashboard.

First:

1\. Propose the greenfield project architecture.  
2\. Propose the PostgreSQL schema required for Phases 1–5.  
3\. Propose the repository/folder structure.  
4\. Define how durable sync jobs will run.  
5\. Define how client isolation will work.  
6\. Define the normalized fact-layer strategy.  
7\. Define authentication architecture without implementing the full client portal.  
8\. Define development/testing environments.  
9\. Identify required environment variables.  
10\. Create an implementation plan for Phase 1 only.

Do not write major application code until this architecture has been reviewed.

The immediate objective is to create a stable foundation that will not need to be replaced when Dashboard, Watch List and Decision Engine are added.  
