# Organic IQ — production readiness review

Scope: readiness for ~35 clients on a daily sync cadence, API-quota and storage
efficiency, and vulnerabilities that could expose API credentials or one
client's data to another.

Reviewed at commit `adaa0e7` (plus the uncommitted UI work). Codebase:
~14.5k LOC Python API + Next.js web app.

Severity key: **P0** blocks launch · **P1** fix in the first weeks · **P2** track.

---

## Summary

The tenant-isolation model is sound — `require_client` resolves the
`X-OrganicIQ-Client-Id` header and checks the caller against `user_clients`
before returning, and every client-scoped route depends on it. Fact tables are
indexed on `(client_id, date)`. No secrets are committed; `.env*` is ignored.

The blockers are elsewhere: two authentication holes, a job-expiry rule that
mass-fails the daily queue at 35-client scale, and a credential-refresh path
whose cost grows with the square of the client count.

| # | Severity | Area | Finding |
|---|----------|------|---------|
| 1 | **P0** | Security | Default secrets are shipped as working fallbacks |
| 2 | **P0** | Security | `/auth/upsert` is unauthenticated and creates privileged users |
| 3 | **P0** | Security | Any unknown `@smamarketing.net` email is auto-provisioned `SMA_ADMIN` |
| 4 | **P0** | Scale | Queued jobs are failed after 45 min — daily sync mass-fails at scale |
| 5 | **P0** | Scale | Worker `importlib.reload()` on every poll cycle |
| 6 | **P1** | Efficiency | Token refresh writes every client's credentials — O(N²) per day |
| 7 | **P1** | Storage | Staging tables are never purged; no `job_id` indexes |
| 8 | **P1** | Quota | GSC/GA4 clients have no retry, backoff, or throttle |
| 9 | **P1** | Scale | Single sequential worker; SE Ranking throttle is process-local |
| 10 | **P1** | Efficiency | Whole result sets buffered in memory and inserted row-by-row |
| 11 | **P2** | Correctness | Two client-scoped tables missing from the delete cascade |
| 12 | **P2** | Ops | OAuth state is in-memory, unbounded, single-process |
| 13 | **P2** | Ops | No rate limiting; internal errors returned to clients |

Findings 1–8 and 11 are fixed in this pass, along with the multi-worker half of
9. Findings 10, 12 and 13 remain open — see "Still open".

---

## P0 — blocks launch

### 1. Default secrets are working fallbacks

`app/core/settings.py` ships usable defaults for both secrets that matter:

```python
auth_secret: str = "dev-auth-secret-change-me"
integration_token_key: str = "dev-integration-token-key-32bytes!!"
```

Both values are in the repo and in `docker-compose.yml`. Nothing validates them
at startup, so a deploy that misses either variable starts silently and looks
healthy.

- **`AUTH_SECRET` unset** — the API accepts any HS256 JWT signed with the
  published string. `get_current_user` trusts the `email` claim, so an attacker
  forges `{"email":"anyone@smamarketing.net"}`, is auto-provisioned `SMA_ADMIN`
  (finding 3), and reads every client's data. Full compromise.
- **`INTEGRATION_TOKEN_KEY` unset** — `crypto.py` derives the Fernet key by
  SHA-256 of that string, so every stored Google refresh token is decryptable by
  anyone who reads the value from the repo and obtains a DB dump.

**Fix:** fail fast at import when `APP_ENV=production` and either secret is a
known default or too short. Implemented — see "Changes applied".

### 2. `/auth/upsert` is unauthenticated

`app/api/routers/auth.py` exposes `POST /auth/upsert` with no dependency, and
`services/auth.py:upsert_user` creates a user with role `SMA_TEAM` (or
`SMA_ADMIN` when the email is in `SMA_ADMIN_EMAILS`), or updates an existing
user's `google_sub`.

Anyone who can reach the API can create staff accounts and overwrite
`google_sub` on existing ones. Today the web `signIn` callback still blocks
non-SMA Google accounts, so this is not by itself a full login bypass — it is a
pre-planted account that becomes live the moment any token for that address is
obtainable, and combined with finding 1 it completes the chain. It is also an
unauthenticated unbounded write.

**Fix:** require a shared internal secret. Implemented.

### 3. Auto-provisioning as `SMA_ADMIN`

`app/core/security.py:get_current_user` — when a token's email is not in the
`users` table:

```python
# Early product phases: any SMA Workspace login is treated as admin.
# Tighten to SMA_ADMIN_EMAILS / team assignments before client portal.
user = User(..., role=UserRole.SMA_ADMIN, is_active=True)
```

Every SMA Workspace address becomes a full admin over all 35 clients on first
request, bypassing `SMA_ADMIN_EMAILS` entirely. The code already flags this as
temporary. It also silently re-creates users you deactivate — deleting a
departing employee's row re-admits them as admin on their next request.

**Fix:** provision at the lowest useful role, admin only via `SMA_ADMIN_EMAILS`.
Implemented.

### 4. Queued jobs are failed after 45 minutes

`services/jobs.py:fail_stale_active_jobs` treats `QUEUED` as an active status
and ages jobs off their `created_at`:

```python
ACTIVE_JOB_STATUSES = (QUEUED, FETCHING, STAGING, NORMALIZING, VALIDATING)
anchor = job.started_at or job.updated_at or job.created_at  # QUEUED → created_at
```

`daily_sync` enqueues every client × every mapped source at once — up to
**6 sources × 35 clients = 210 jobs**. The worker drains them one at a time. Any
job still waiting 45 minutes after enqueue is marked `FAILED` with "Timed out
after 45 minutes while syncing (stuck job cleared)" — despite never having run.

At 35 clients only the first few minutes of the queue survive. This is the
single defect most certain to break the daily sync at target scale, and it
fails *silently*, as ordinary job failures.

**Fix:** age out only jobs that actually started; add a separate, much longer
ceiling for queue backlog. Implemented.

### 5. Worker hot-reloads modules every cycle

`app/worker.py:_jobs_module()` calls `importlib.reload()` on `app.services.jobs`
plus 12 ingestion modules on **every poll iteration** (every ~2s when idle).

This is a development convenience running in production. Beyond the wasted CPU,
reloading modules that define SQLAlchemy models and enums re-creates those
classes, so identity comparisons and mapper registrations can break in ways that
surface as sporadic job failures — the code already concedes this by catching
the exception and logging "restart worker after model changes".

**Fix:** gate on `APP_ENV`. Implemented.

---

## P1 — fix early

### 6. Token refresh cost grows with the square of client count

`ingestion/google_credentials.py:access_token_for_client` does two expensive
things on every single call:

1. `ensure_access_token()` — an unconditional Google OAuth refresh. Access
   tokens are never cached; the comment says "Always mint a fresh Google access
   token".
2. `persist_google_tokens()` → `propagate_google_credentials()` — loops over
   **every client** and rewrites the encrypted credential blob on both the GSC
   and GA4 rows, then commits.

So one call = 1 Google token request + `2 × N_clients` encrypted row writes.

It is called four times per client per daily cycle (`fetch_gsc_pages`,
`fetch_gsc_daily`, `fetch_gsc_queries`, `fetch_ga4`). At 35 clients:

```
4 refreshes × 35 clients                    = 140 Google token requests/day
140 refreshes × 70 credential row writes    ≈ 9,800 encrypted writes/day
```

Writes scale as O(N²) — at 100 clients it is ~80,000/day. It also commits mid-job,
which interleaves with the job's own transaction.

**Fix (applied):** cache the token per refresh token for its real lifetime and
delete the propagation from the refresh path. The stored access token was never
read back — only `refresh_token` is — so persisting it bought nothing.
`persist_google_tokens` is removed so the path cannot be reintroduced; a
reconnect clears the cache. A daily cycle now costs roughly **one** token
request instead of 140, and zero credential writes instead of ~9,800.

### 7. Staging tables are never purged, and lack `job_id` indexes

Each fetch clears its own rows with `DELETE ... WHERE job_id = <this job>`, but
`job_id` is unique per job, so that never matches a previous run. Only
`publish_audit.py` deletes staging rows after publishing. Every other staging
table — GSC pages/daily/query-pages, GA4 traffic/events, all SE Ranking staging —
**grows forever**, and each row also stores the full API response in a `raw`
JSON column.

`staging_gsc_query_pages` is the worst: grain is
`date × query × page × country × device`. A mid-size site easily produces tens
of thousands of rows per day; times 35 clients times 365 days this is the
dominant storage cost in the system, and none of it is read after publish.

Compounding it: of the 15 staging tables, only `staging_ser_audit_issues`
declares a `job_id` index. Every fetch-time `DELETE ... WHERE job_id` and every
publish-time read is a sequential scan over a table that only ever grows.

**Fix (applied):** `ingestion/staging_cleanup.py` purges a job's staging rows
after a successful publish, wired into the GSC and GA4 pipelines (SE Ranking
audit already did this). Migration `0023` adds the 13 missing `job_id` indexes
plus `sync_jobs(status, created_at)` and `sync_jobs(client_id, created_at)`;
migration `0024` deletes the accumulated backlog for jobs already in a terminal
state. A test asserts every registered job source has a purge mapping, so a new
source cannot silently start leaking again.

### 8. GSC and GA4 clients have no retry, backoff, or throttle

`ingestion/gsc/client.py` and `ingestion/ga4/client.py` call `raise_for_status()`
directly. A single 429 or transient 503 fails the whole job. Neither honours
`Retry-After`, and neither throttles.

SE Ranking (`ingestion/seranking/client.py`) is the model to copy — it throttles
to ~4.5 rps, retries 3×, and handles 429 explicitly.

This matters most once syncs are parallelised (finding 9): concurrent GSC calls
against one Google project will draw 429s, and today that means failed jobs
rather than slower ones.

**Fix (applied):** `ingestion/google_http.py` retries 408/429/5xx and connection
errors with exponential backoff plus jitter, honours `Retry-After`, and raises
other 4xx immediately (a 403 for a revoked scope should not burn three more
calls). Both Google clients route through it; a test asserts neither calls
`raise_for_status()` directly again.

### 9. Single sequential worker; SE Ranking throttle is process-local

`worker.py:main()` processes one job at a time. `claim_next_job` already uses
`FOR UPDATE SKIP LOCKED`, so **running multiple worker processes is safe** and
is the natural fix.

Two caveats before scaling out:

- `seranking/client.py` throttles via a module-level `_last_request_at` global.
  That is per-process, so N workers issue N × 4.5 rps and will exceed SE
  Ranking's 5 rps limit. Needs a shared limiter (Redis token bucket) or a
  dedicated single-concurrency queue for SE Ranking sources.
- ~~`daily_sync.maybe_run_daily_sync` reads then writes `SchedulerCheckpoint`
  without a row lock.~~ **Fixed** — the checkpoint is now selected
  `FOR UPDATE`, with the insert race handled, so two workers cannot both
  enqueue the cycle.

Throughput is unmeasured — worth timing one full cycle for your largest client
before picking a worker count. The `se_ranking_audit` source is the long pole
(its own client allows up to 20 minutes per audit fetch).

### 10. Result sets are buffered in memory and inserted row-by-row

`query_search_analytics` paginates 25,000 rows at a time into a single list and
returns it whole; the caller then does `db.add()` per row and one commit at the
end. For `gsc_queries` that is potentially hundreds of thousands of heavy ORM
objects resident at once — a plausible worker OOM, and slow regardless.

`bulk_save_objects` is already used in the SE Ranking audit path; the same
treatment applied to GSC/GA4 with chunked commits would fix both memory and speed.

---

## P2 — track

### 11. Two client-scoped tables missing from the delete cascade

`services/clients.py:_CLIENT_CASCADE_TABLES` omitted `facts_crawl_page_issues`
and `staging_ser_audit_issues`, both of which carry `client_id`. Deleting a
client either tripped a foreign key or stranded that client's crawl data — a
data retention problem if a client asks to be removed. **Fixed**: both added,
and the full model set re-checked against the list.

### 12. OAuth state is in-memory, unbounded, single-process

`oauth_google.py:_oauth_states` is a module dict. Entries are never expired, so
repeated `/oauth/google/start` calls grow it without limit. More practically, it
breaks the moment the API runs more than one process or replica: state written
on worker A is missing when Google's callback lands on worker B, and the user
sees `invalid_state`. Move it to the DB or Redis with a TTL before scaling the
API tier.

Related: `google_data_oauth_redirect_uri` defaults to `http://127.0.0.1:8000/...`
and must be HTTPS in production.

Also worth noting by design: `propagate_google_credentials` stores the *same*
workspace refresh token on all 35 clients' rows. That is intentional (one SMA
Google grant covers all properties), but it means there is no per-client
credential isolation, and one leaked row leaks the grant for every client.

### 13. No rate limiting; internal errors surface to clients

No rate-limit middleware on the FastAPI app — `/auth/upsert` and the OAuth start
endpoint are the exposed unauthenticated surfaces. Several handlers also return
`detail=str(exc)` from upstream failures, which leaks internal messages and
occasionally upstream URLs to the client. Prefer a generic message plus a
server-side log.

CORS is correctly restricted via `ALLOWED_ORIGINS`; keep it off `*`, since
`allow_credentials=True` is set.

---

## Changes applied in this pass

Findings 1–8 and 11, plus the multi-worker safety half of 9. 28 regression tests
in `tests/test_production_hardening.py` pin each one; the full suite is 155 green.

| Area | Change |
|------|--------|
| Secrets | `APP_ENV=production` refuses to boot on default/short `AUTH_SECRET`, `INTEGRATION_TOKEN_KEY`, missing `INTERNAL_API_SECRET`, or wildcard CORS |
| Auth | `POST /auth/upsert` requires `X-OrganicIQ-Internal-Secret` (constant-time compare); web app sends it |
| Auth | Unknown workspace logins provision as `SMA_TEAM`; admin only via `SMA_ADMIN_EMAILS` |
| Jobs | Queued and running jobs age on separate clocks — a long backlog no longer mass-fails |
| Worker | Hot reload gated to non-production |
| Quota | Google access tokens cached; O(N²) credential propagation deleted |
| Quota | Retry/backoff/`Retry-After` for GSC + GA4 |
| Storage | Staging purged after publish; backlog deleted; 15 hot-path indexes added |
| Scale | Scheduler checkpoint locked `FOR UPDATE` |
| Correctness | Client delete cascade completed |

## Deployment prerequisites

Set on the Railway API **and** worker:

```
APP_ENV=production
AUTH_SECRET=<32+ bytes, same as Vercel>
INTEGRATION_TOKEN_KEY=<32+ bytes, stable — rotating it orphans stored Google grants>
INTERNAL_API_SECRET=<32+ bytes, same as Vercel>
```

and on Vercel: `AUTH_SECRET`, `INTERNAL_API_SECRET` (matching values).

Generate each with `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
Then run `alembic upgrade head` (migrations 0023 and 0024).

The API will refuse to start if any of these is missing — that is deliberate, and
it is how you find out before traffic does rather than after.

## Still open

1. **Measure one full daily cycle** before launch (finding 9). This is the one
   remaining unknown for the 35-client target: nothing in the code tells us how
   long a real cycle takes, and `se_ranking_audit` alone permits 20 minutes per
   client. Time a cycle against your largest client, multiply, and size the
   worker count from that. Multiple workers are now safe for GSC/GA4.
2. **Shared SE Ranking rate limiter** before running >1 worker (finding 9) —
   its 4.5 rps throttle is a process-global, so N workers means N × 4.5 rps
   against a 5 rps ceiling. Until then, either keep one worker or route SE
   Ranking sources to a dedicated single-concurrency queue.
3. **Chunked bulk inserts for GSC/GA4 fetch** (finding 10). Publish already
   batches; fetch still buffers the whole result set and `db.add()`s per row,
   which is the likeliest cause of a worker OOM on a large `gsc_queries` pull.
4. **Durable OAuth state + rate limiting** (findings 12, 13) — required before
   running more than one API process, and worth doing regardless.
