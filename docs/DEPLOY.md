# Organic IQ — deploy checklist (Railway + Vercel)

Use with [README → Deploy](../README.md#deploy-railway--vercel) and [`.env.example`](../.env.example) Production section.

## Services

| Name | Platform | Root / image | Start command | Public? |
|------|----------|--------------|---------------|---------|
| Postgres | Railway plugin | — | — | private |
| api | Railway | `apps/api` Dockerfile | `scripts/start-api.sh` | yes |
| worker | Railway | same Dockerfile | `scripts/start-worker.sh` | no |
| web | Vercel | Root Directory `apps/web` | Next build | yes |

## Env matrix

| Variable | Vercel web | Railway api | Railway worker |
|----------|:----------:|:-----------:|:--------------:|
| `AUTH_SECRET` | required (shared) | required (shared) | required (shared) |
| `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` | required | — | — |
| `AUTH_URL` / `NEXTAUTH_URL` | `https://<vercel-host>` | — | — |
| `AUTH_TRUST_HOST` | `true` | — | — |
| `API_URL` / `NEXT_PUBLIC_API_URL` | `https://<api-host>` | — | — |
| `SMA_GOOGLE_HOSTED_DOMAIN` | `smamarketing.com` | `smamarketing.com` | `smamarketing.com` |
| `DATABASE_URL` | — | from Postgres | from Postgres |
| `INTEGRATION_TOKEN_KEY` | — | required (shared) | required (shared) |
| `SMA_ADMIN_EMAILS` | — | required | required |
| `ALLOWED_ORIGINS` | — | `https://<vercel-host>` | optional |
| `WEB_APP_URL` | — | `https://<vercel-host>` | optional |
| `GOOGLE_DATA_OAUTH_*` | — | required | optional |
| `GOOGLE_DATA_OAUTH_REDIRECT_URI` | — | `https://<api-host>/oauth/google/callback` | — |
| `SE_RANKING_API_KEY` | — | required for SE syncs | required for SE syncs |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | — | required for keyword pricing, competitor reads and SERP features | same (whichever service runs jobs) |
| `DECISION_ENGINE_ENABLED` | — | `true` | optional |
| `WORKER_POLL_INTERVAL_SECONDS` | — | — | `2` (default) |
| `DAILY_SYNC_ENABLED` | — | `true` | `true` |
| `DAILY_SYNC_HOUR_UTC` | — | `11` (~7am ET) | same |
| `DAILY_SYNC_LOOKBACK_DAYS` | — | `3` | same |

## Google Console

| Client | Origin | Redirect |
|--------|--------|----------|
| Login (Auth.js) | `https://<vercel-host>` | `https://<vercel-host>/api/auth/callback/google` |
| Data (GSC/GA4) | — | `https://<api-host>/oauth/google/callback` |

## After first API deploy

```bash
# Railway one-off / shell on api service — once only
python -m app.seed
```

Confirm: `curl -s https://<api-host>/health` → `{"status":"ok"}`.

## Smoke test

- [ ] Vercel login with `@smamarketing.com`
- [ ] Client switcher shows SMA Marketing (after seed)
- [ ] Dashboard / Decision Engine load without hard errors
- [ ] GSC or GA4 OAuth connect completes and returns to web
- [ ] Short sync job moves to completed/partial; Data Health updates
- [ ] Annotations page and baseline preview reachable


---

# Organic IQ v2: deploy additions

v2 is a second web app (`apps/web-v2`) on the **same API and Postgres** as the live tool. The API only gets
additive migrations, so the live tool keeps working while both run. Nothing below replaces the section above;
it adds to it.

## Services

| Name | Platform | Root / image | Start command | Public? |
|------|----------|--------------|---------------|---------|
| web-v2 | Vercel (a **new** project) | Root Directory `apps/web-v2` | Next build | yes |
| api, worker, Postgres | Railway | unchanged | unchanged | unchanged |

Create the Vercel project from the same GitHub repo, set the Root Directory to `apps/web-v2`, and leave the
framework preset on Next.js.

## Vercel env (web-v2)

| Variable | Value |
|----------|-------|
| `AUTH_SECRET` | same value as the API's |
| `AUTH_GOOGLE_ID` / `AUTH_GOOGLE_SECRET` | the login OAuth client |
| `AUTH_URL` / `NEXTAUTH_URL` | `https://<v2-vercel-host>` |
| `AUTH_TRUST_HOST` | `true` |
| `API_URL` / `NEXT_PUBLIC_API_URL` | `https://<api-host>` |
| `INTERNAL_API_SECRET` | same value as the API's (v2 refuses to sign anyone in without it) |
| `SMA_GOOGLE_HOSTED_DOMAIN` | `smamarketing.com` |

## Railway env: new for v2

Set on **api** and **worker** unless noted. The worker is what runs the scheduled jobs, so it needs the keys too.

| Variable | api | worker | What it does |
|----------|:---:|:------:|--------------|
| `ALLOWED_ORIGINS` | add `https://<v2-vercel-host>` (comma separated, keep the old one) | — | lets v2's browser calls through |
| `WEB_V2_APP_URL` | `https://<v2-vercel-host>` | — | where Google connect returns to |
| `BING_WEBMASTER_API_KEY` | yes | yes | Bing status on Connections, weekly Bing pull |
| `OPENAI_API_KEY` | yes | yes | LLM visibility: ChatGPT |
| `PERPLEXITY_API_KEY` | yes | yes | LLM visibility: Perplexity |
| `GEMINI_API_KEY` | yes | yes | LLM visibility: Gemini (needs prepaid credit in AI Studio) |
| `ANTHROPIC_API_KEY` | yes | yes | LLM visibility: Claude, and finding other brands in answers |
| `TEAMWORK_SITE` / `TEAMWORK_API_TOKEN` | yes | — | Send to Teamwork, and listing projects and tasklists |

A platform with no key is skipped, not failed. A key typed with a missing `=` is silently ignored, so check the
**Variables** list shows each name with a value.

## Migrations

`scripts/start-api.sh` runs Alembic on each API start. v2 adds **0070 to 0082** on top of the live chain
(baseline `0069_ga4_native_channels`). They only add tables and columns; a test
(`tests/test_migrations_additive_only.py`) refuses anything else. Run them against a **copy of the production
database first** if Railway lets you, and confirm `/health` answers `{"status":"ok","migrations":"..."}` after.

## Sign-in domain

Production uses `SMA_GOOGLE_HOSTED_DOMAIN=smamarketing.com` on the API, the worker and web-v2. The code's own default is also
`smamarketing.com` only, so **a staff account still on `.net` is refused**. Check every person who signs in has a `.com`
account, and that `SMA_ADMIN_EMAILS` lists `.com` addresses.

One deliberate exception: `IDENTITY_DOMAINS` still lists both domains. It is not about signing in. It matches a person
between systems (Teamwork still holds 7 of 8 people on `.net`), so removing `.net` there would leave their tasks
unassigned. Drop it once Teamwork is moved.

## Google Console

| Client | Add |
|--------|-----|
| Login (Auth.js) | origin `https://<v2-vercel-host>`, redirect `https://<v2-vercel-host>/api/auth/callback/google` |
| Data (GSC/GA4) | nothing: its redirect goes to the API, which does not move |

## What starts running once the worker has the keys

- Daily: Search Console, GA4 and SE Ranking syncs (as before).
- Weekly: the site crawl, and the Bing pull for any client with a Bing site saved.
- Every 28 days: an LLM visibility run for each worked client with paired prompts.

**An LLM run asks every prompt of every platform that has a key** (about $0.08 for 30 prompts on four
platforms). Check the keys before the first scheduled day.

## v2 smoke test

- [ ] Sign in at the v2 address with `@smamarketing.com`; the client switcher lists the clients
- [ ] Monthly review loads, with the "Data through" line under the header
- [ ] Settings → Connections: Google, Search Console, Bing and Teamwork show their state
- [ ] Decision engine: a candidate list loads; diagnose one page; the growth action builds
- [ ] Confirm a growth action and send it to Teamwork; the task appears in the client's tasklist
- [ ] LLM visibility: Setup shows each platform as ready; Run now queues a job and the worker picks it up
- [ ] The live tool still loads for a client (nothing in v2 should have changed it)
