# Organic IQ copilot: base model choice and plan

Status: proposal, 2026-10-15. Nothing built yet.

## Goal

An in-app assistant that sits on top of client data (GSC, GA4, SE Ranking, crawl,
keyword map, decision engine output) and the Organic IQ process, so a user can:

1. get a summary report for a client/month in SMA's voice,
2. check the tool ("is this client's data fresh? did the sync fail?"),
3. diagnose ("why did clicks drop on /services?"),
4. take action (assign a slot, send to Teamwork, re-run a sync) with confirmation.

## What already exists (and shapes the design)

- The decision engine, slots, update catalog and results loop are **deterministic
  rules** (`apps/api/app/decisions/`). Keep it that way. The model must not decide
  what the plan is; it explains, retrieves, summarises and calls the engine.
- There is no LLM code in the repo today, so there are no logs to train on yet.
- Hosting is Railway (no GPUs) plus Vercel. Any self-hosted model needs separate
  GPU hosting.

## Julius AI vs build

Julius AI is a standalone "upload data, chat, get charts" product. It is a good
tool for an analyst's ad-hoc questions, but it cannot be embedded as your
in-app copilot, cannot call your actions (assign slot, Teamwork), does not know
the Organic IQ process, and would require exporting client data out of your
stack. Use it, if at all, as an analyst's side tool. It is not a substitute for
the feature. The real choice is between (A) a hosted frontier model with tools
and (B) a fine-tuned small model.

| | A. Hosted frontier model + tools + retrieval | B. Fine-tuned small model |
|---|---|---|
| Time to first useful version | 2-3 weeks | 3-4 months |
| Tool calling / multi-step diagnosis | Strong | Weaker; needs training data |
| Voice and process adherence | Via system prompt + playbook retrieval | Via fine-tune |
| Cost per request | Highest per call, tiny at agency scale | Lowest at high volume |
| Data leaves your infra | Yes (API, zero-retention terms) | No, if self-hosted |
| Ops burden | None | GPU hosting, evals, retraining |

**Recommendation: start with A, collect real usage, then distil into B only for
the narrow tasks where it pays off.** Fine-tuning a base model on SEO/GEO best
practices before you have an eval set and real conversations is the most common
way this project goes wrong. Most of "best practices" is better delivered as
retrieved playbook text than baked into weights (it changes quickly, and GEO
especially).

## Base model shortlist (if/when we do B)

Checked against the Hugging Face Hub on 2026-10-15; licenses come from
third-party roundups and **must be confirmed on each model card before commit**.

| Candidate | Sizes on Hub | Why | Watch-outs |
|---|---|---|---|
| **Qwen3.5** (Mar-Apr 2026) | 0.8B, 2B, 4B, 9B, 27B, 35B-A3B; `-Base` variants | Reported Apache 2.0, strong tool calling, huge community/tooling, 9B has 8.6M downloads | Tool-use quality varies by size |
| **Gemma 4** (Jul 2026) | E2B, E4B, 12B, 26B-A4B, 31B; QAT 4-bit variants | Reported Apache 2.0 (Gemma 3 was not), good 12B size, official quantized builds | Verify license text; older guides describe the earlier Gemma terms |
| **Qwen3.8-27B** (Aug 2026) | 27B | Newest Qwen, 7.3M downloads | Larger than "small"; 27B costs real GPU money |
| Phi-4-mini (MIT), SmolLM3-3B (Apache), Llama 3.x | | Fallbacks | Llama license is restrictive; Phi/SmolLM are older |

**Pick for the pilot: Qwen3.5-9B (instruct) with LoRA, with Gemma 4 12B as the
bake-off challenger.** 9B-12B is the smallest class that reliably handles
structured tool calls plus a grounded paragraph of analysis. Go to 4B only for
single-purpose tasks (classify intent, draft a summary from a fixed JSON).

Do not use "uncensored" or merged community fine-tunes seen in the trending list
as a base. Start from the official instruct or base checkpoint.

## Architecture (same for A and B)

```
Web (Next.js chat panel)
   -> API /copilot  (FastAPI, auth + client scoping)
        -> model gateway (provider-agnostic; swap hosted <-> SLM by config)
        -> tools (read-only first):
             get_client_summary, get_gsc_trend, get_page_signals,
             get_sync_status, get_decision_plan, get_content_opp_plan,
             search_playbook (RAG over OIQ process + SEO/GEO guidance)
        -> action tools (write, require user confirm in UI):
             assign_slot, send_to_teamwork, trigger_sync
   -> audit log: every prompt, tool call, result, user rating  (this becomes the training set)
```

Rules that matter:

- **Numbers come from tools, never from the model.** Reports are templated
  structures filled by the API; the model writes narrative around them and cites
  the figure's source.
- **Client scoping enforced server-side** in each tool, not in the prompt.
- **Writes are proposals.** The model returns an action card; the user clicks
  confirm. No autonomous writes in v1.
- **Gateway abstraction from day one**, so model B drops in behind the same API.

## Phases

**Phase 0: Define and measure (week 1-2).** Write 100-200 real tasks across the
four jobs (summaries, tool checks, diagnosis, actions) with reference answers or
rubrics, drawn from past SMA reports and Teamwork tickets. Build the eval
harness (rubric + LLM judge + hard checks that figures match tool output). This
is the asset everything else depends on.

**Phase 1: Hosted-model copilot, read-only (week 2-5).** Gateway, read tools,
playbook RAG (OIQ process doc, the build spec, GEO/SEO standards, your per-brand
briefs), monthly summary report, "check the tool" diagnostics. Ship to SMA
internal users first (the SMA Marketing test client).

**Phase 2: Diagnose and act (week 5-9).** Diagnosis flows that chain tools
(drop in clicks -> page signals -> candidate causes -> engine prescription), and
confirmed write actions. Thumbs up/down and edit-capture on every output.

**Phase 3: Decide whether to build B (week 10+).** Only proceed if one of these
is true: monthly API spend is material, clients require data not leave your
infra, or latency/consistency of a specific task is a problem. Then:

1. Export logged, rated, human-corrected examples (target 2-5k clean examples;
   do not train on raw logs).
2. LoRA/QLoRA SFT on Qwen3.5-9B, same on Gemma 4 12B; optionally preference
   tuning on the rated pairs.
3. Score both against the Phase 0 eval and against the hosted model. Promote
   only if within a few points on quality and clearly ahead on cost/latency, and
   route per task (the SLM for summaries, the hosted model for hard diagnosis).
4. Serve with vLLM on a GPU host (Modal, RunPod, Together or Fireworks LoRA
   hosting). Railway cannot do this.

## Risks

- Training before evals exist: you cannot tell if the model got better.
- Baking fast-moving GEO guidance into weights: keep it in retrieval.
- Hallucinated metrics in client-facing reports: enforce tool-sourced numbers
  and a validator that rejects figures not in the tool payload.
- Client data in prompts: confirm provider zero-retention terms and add this to
  client contracts before any external client sees the feature.
- Prompt injection via crawled page content or GSC query strings flowing into
  prompts: treat all tool output as data, and never let it trigger write tools
  without a user confirm.

## Decisions needed

1. Must client data stay inside your infrastructure (drives A vs B early)?
2. Who sees it first: SMA staff only, or clients too?
3. Where do past reports and process docs live, so we can build the eval set
   and playbook corpus?

## Update 2026-10-15: decisions and what is built

- **No Anthropic.** The copilot runs on Qwen behind any OpenAI-compatible
  endpoint (`LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`). Start with stock
  Qwen3.5-9B instruct on a hosted endpoint; point `LLM_MODEL` at a fine-tuned
  LoRA when one beats it on the eval set. Hosted inference is acceptable; no
  self-hosting requirement.
- **Playbook** is the Organic IQ process (condensed from the decision-engine
  spec) plus Ahrefs and HubSpot published guidance, in
  `apps/api/app/copilot/knowledge/`.
- **Scaffold built** on branch `feat/copilot-scaffold`: `app/copilot/` (gateway,
  tools, chat loop, playbook search), tables `copilot_conversations` and
  `copilot_messages` (migration 0059), `POST /copilot/chat` and
  `POST /copilot/messages/{id}/rating`, staff only.
- **Honest risk:** a 9B model is weaker at multi-step tool use and diagnosis than
  a frontier model. Stock Qwen first, measure against the eval set, then
  fine-tune. Training data bootstraps from the deterministic engine (facts in,
  prescription and explanation out) and from rated conversations; Qwen3.8-27B is
  an open-weights option for generating drafts to be corrected by hand.
- **Not built yet:** the web chat panel, write actions (assign, send to
  Teamwork), streaming, the eval set.
