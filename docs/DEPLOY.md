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
| `SMA_GOOGLE_HOSTED_DOMAIN` | `smamarketing.net` | `smamarketing.net` | `smamarketing.net` |
| `DATABASE_URL` | — | from Postgres | from Postgres |
| `INTEGRATION_TOKEN_KEY` | — | required (shared) | required (shared) |
| `SMA_ADMIN_EMAILS` | — | required | required |
| `ALLOWED_ORIGINS` | — | `https://<vercel-host>` | optional |
| `WEB_APP_URL` | — | `https://<vercel-host>` | optional |
| `GOOGLE_DATA_OAUTH_*` | — | required | optional |
| `GOOGLE_DATA_OAUTH_REDIRECT_URI` | — | `https://<api-host>/oauth/google/callback` | — |
| `SE_RANKING_API_KEY` | — | required for SE syncs | required for SE syncs |
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

- [ ] Vercel login with `@smamarketing.net`
- [ ] Client switcher shows SMA Marketing (after seed)
- [ ] Dashboard / Decision Engine load without hard errors
- [ ] GSC or GA4 OAuth connect completes and returns to web
- [ ] Short sync job moves to completed/partial; Data Health updates
- [ ] Annotations page and baseline preview reachable
