# ARIA Deployment Runbook

## Architecture

| Component | Platform | URL |
|-----------|----------|-----|
| Backend API | Render (Web Service) | `https://aria-api.onrender.com` |
| Scheduled Tasks | Render (Cron) | N/A (runs every 15 min) |
| Frontend | Vercel | `https://app.luminone.ai` |
| Database | Supabase | `https://<project>.supabase.co` |
| Knowledge Graph | Neo4j (Aura or self-hosted) | `bolt://<host>:7687` |

---

## Pre-Deploy Checklist

Before pushing to `main`:

- [ ] All tests pass: `cd backend && pytest tests/ -v`
- [ ] Type checking passes: `mypy src/ --strict`
- [ ] Linter passes: `ruff check src/`
- [ ] No secrets in code: check for hardcoded API keys, tokens
- [ ] Database migrations ready (if schema changes)
- [ ] Frontend builds cleanly: `cd frontend && npm run build`
- [ ] Frontend type checking: `npm run typecheck`

---

## How to Deploy

### Backend (Render)

**Auto-deploy:** Push to `main` branch. Render detects the push and auto-deploys.

```bash
git push origin main
```

Monitor the deploy at: Render Dashboard → aria-api → Events

### Frontend (Vercel)

**Auto-deploy:** Push to `main` branch. Vercel detects the push and auto-deploys.

Monitor at: Vercel Dashboard → aria-frontend → Deployments

---

## How to Rollback

### Backend

1. Go to **Render Dashboard → aria-api → Events**
2. Find the last known-good deploy
3. Click the deploy → **Rollback to this deploy**

### Frontend

1. Go to **Vercel Dashboard → aria-frontend → Deployments**
2. Find the last known-good deployment
3. Click **...** → **Promote to Production**

---

## Database Migrations

### Running Migrations Against Production Supabase

1. **Via Supabase Dashboard:**
   - Go to `https://supabase.com/dashboard/project/<project-id>/sql`
   - Paste migration SQL and execute

2. **Via Supabase CLI:**
   ```bash
   cd backend
   supabase db push --linked
   ```

3. **Migration files location:** `backend/supabase/migrations/`

### Migration Safety Rules

- Always test migrations locally first against a development Supabase instance
- Use `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`
- Never drop columns or tables without verifying no active code references them
- Back up production data before destructive migrations

---

## Environment Variables Reference

All secrets must be set manually in the Render Dashboard (they are not synced from `render.yaml`).

### Required

| Variable | Description |
|----------|-------------|
| `APP_SECRET_KEY` | Application secret for JWT signing and encryption |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key for LLM operations |
| `SUPABASE_URL` | Supabase project URL (e.g., `https://xxx.supabase.co`) |
| `SUPABASE_ANON_KEY` | Supabase anonymous/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key (bypasses RLS) |
| `OPENAI_API_KEY` | OpenAI key (required by Graphiti for embeddings) |

### Optional — Services

| Variable | Description |
|----------|-------------|
| `NEO4J_URI` | Neo4j connection URI (default: `bolt://localhost:7687`) |
| `NEO4J_USER` | Neo4j username (default: `neo4j`) |
| `NEO4J_PASSWORD` | Neo4j password |
| `TAVUS_API_KEY` | Tavus API key for avatar/video |
| `TAVUS_PERSONA_ID` | Tavus persona ID |
| `TAVUS_REPLICA_ID` | Tavus replica ID |
| `TAVUS_CALLBACK_URL` | Webhook callback URL for Tavus events |
| `DAILY_API_KEY` | Daily.co API key for WebRTC |
| `EXA_API_KEY` | Exa API key for web research/enrichment |
| `EXA_WEBHOOK_SECRET` | Exa webhook signature verification |
| `COMPOSIO_API_KEY` | Composio API key for OAuth integrations |
| `STRIPE_SECRET_KEY` | Stripe secret key for billing |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signature verification |
| `RESEND_API_KEY` | Resend API key for transactional email |

### Application Config

| Variable | Description | Default |
|----------|-------------|---------|
| `APP_ENV` | Environment: `development`, `staging`, `production` | `development` |
| `LOG_FORMAT` | Logging format: `json` (production), `text` (dev) | `text` |
| `LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` | `INFO` |
| `CORS_ORIGINS` | Comma-separated allowed CORS origins | `http://localhost:3000,http://localhost:5173` |
| `ENABLE_SCHEDULER` | Enable in-process scheduler (`true`/`false`) | `true` |
| `PYTHON_VERSION` | Python runtime version on Render | `3.11.7` |

---

## Checking Logs

### Render Dashboard

1. Go to **Render Dashboard → aria-api → Logs**
2. Logs are structured JSON in production (`LOG_FORMAT=json`)
3. Filter by searching for `request_id`, `service`, or `level`

### Render MCP (via Claude Code)

Set up Render MCP for direct access from Claude Code:

```bash
claude mcp add --transport http render https://mcp.render.com/mcp \
  --header "Authorization: Bearer <RENDER_API_KEY>"
```

Get your Render API key from: **dashboard.render.com → Account Settings → API Keys**

Once connected, Claude Code can query logs, check deployment status, and monitor services directly.

---

## Health Checks

### Endpoints

| Endpoint | Auth | Purpose |
|----------|------|---------|
| `/health` | None | Root health check (Render healthCheckPath) — returns 200 if process is alive |
| `/api/v1/health` | None | Full dependency check (Supabase, Tavus, Claude, Exa). Returns 503 if DB is down |
| `/api/v1/health/ping` | None | Lightweight ping with timestamp for UptimeRobot/external monitors |
| `/api/v1/health/detailed` | Admin | Circuit breakers, error summary, memory, full dependency checks |

### Health Status Logic

- **healthy** — All dependencies reachable
- **degraded** — DB is up but a non-critical service (Tavus, Claude, Exa) is down
- **unhealthy (503)** — Database is down → Render auto-restarts the instance

### Setting Up UptimeRobot

1. Create free account at [uptimerobot.com](https://uptimerobot.com)
2. Add HTTP(s) monitor: `https://aria-api.onrender.com/api/v1/health/ping`
3. Check interval: 5 minutes
4. Alert contacts: your email/Slack

---

## Render Startup Program

For cost savings on infrastructure:

1. **Launch tier (no VC required):** Apply at [render.com/startups](https://render.com/startups)
2. **Build tier ($5K credits):** Requires VC intro — apply once funded

---

## Troubleshooting

### Backend won't start

1. Check Render Events for build/deploy errors
2. Verify all required env vars are set in Render Dashboard
3. Check if `requirements.txt` has dependency conflicts
4. Review logs for import errors or missing modules

### Health check returning 503

1. Check `/api/v1/health` to see which service is down
2. If Supabase is down: check Supabase dashboard for outages
3. If circuit breakers are OPEN: check `/api/v1/health/detailed` (admin) for error history

### Slow response times

1. Check `/api/v1/perf-stats` for p50/p95/p99 latency by endpoint
2. Look for `[SLOW_QUERY]` entries in logs (requests > 500ms)
3. Check Supabase query performance in the Supabase dashboard

### Frontend 404 on routes

Vercel is configured with SPA rewrites in `frontend/vercel.json`. If routes return 404, verify the rewrite rules are correct.
