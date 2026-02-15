# ACRON — Inference Cost Optimizer

**ACRON** reduces LLM inference costs by **85–97%** through intelligent routing, multi-tier caching, and workflow decomposition. It provides a REST API, OpenAI-compatible endpoint, and a full dashboard for metrics, analytics, and cache management.

---

## Features

- **Smart routing** — Autopilot (task-aware), Guided (quality/latency preferences), or Explicit (fixed model). Routes to the most cost-efficient model that meets your constraints.
- **Three-tier cache** — Tier 1: exact match (Redis or in-memory). Tier 2: semantic similarity (Cohere embeddings). Tier 3: intermediate workflow results.
- **Dashboard** — Next.js app: Dashboard, Get Started, Inference, Cache, Analytics, Profile, Settings. Metrics, cost breakdown, trends, and recent inferences are **per-organization** (no cross-account data).
- **Auth & multi-tenancy** — Sign up / log in (email + password). API keys stored in PostgreSQL; validation via `Authorization: Bearer <key>` or `x-api-key`. Scopes: `infer`, `analytics`, `admin`, `all`. Default signup keys get `admin` (full access).
- **Observability** — Cost and latency tracking, cache hit rates, quality score (from model registry), cost breakdown by model, time-series trends, forecasting, anomaly detection, Prometheus export.

---

## How It Works

```
Request → Auth (API key) → Cache (T1 → T2 → T3) → Router → LLM → Track → Response
```

1. **Auth** — Validate API key (Bearer or `x-api-key`); resolve `org_id` for scoped metrics.
2. **Cache** — Exact match (T1), then semantic similarity (T2), then intermediate (T3). On hit, return cached response and log event.
3. **Router** — Select model by quality/latency/cost (autopilot or guided) or use explicit model.
4. **Inference** — Call OpenAI or Anthropic (or mock). Log event with cost, tokens, cache hit, quality.
5. **Analytics** — Metrics, recent inferences, cost breakdown, and trends are filtered by `org_id`.

---

## Quick Start

### Backend (API)

```bash
# Clone and install
git clone <repo-url>
cd asahi
pip install -r requirements.txt

# Environment
cp .env.example .env
# Edit .env: add OPENAI_API_KEY, ANTHROPIC_API_KEY, COHERE_API_KEY.
# For signup/login and API key storage: set DATABASE_URL (PostgreSQL).
# For Tier 1 Redis cache: set REDIS_URL (or REDIS_PRIVATE_URL, REDIS_TLS_URL, REDISCLOUD_URL).

# Run API (default port 8000)
python main.py api
# Or with uvicorn directly (e.g. for production):
# uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8000
```

- **Health:** [http://localhost:8000/health](http://localhost:8000/health)  
- **Interactive docs:** [http://localhost:8000/docs](http://localhost:8000/docs)  
- **OpenAPI JSON:** [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### Frontend (Dashboard)

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Then:

1. **Sign up** (or log in) — creates an org and returns an API key (stored in browser).
2. **Settings** — Set API base URL to `http://localhost:8000` if not already (or use `NEXT_PUBLIC_API_URL`).
3. **Inference** — Run a prompt; use Autopilot, Guided (quality/latency), or Explicit (model name).
4. **Dashboard / Cache / Analytics** — View org-scoped metrics, cost, cache hit rate, recent inferences, cost breakdown, and trends.

---

## API Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health, cache backend (redis/memory), version |
| `/infer` | POST | Run inference (prompt, routing_mode, quality_preference, latency_preference, model_override, etc.) |
| `/v1/chat/completions` | POST | OpenAI-compatible chat completions |
| `/metrics` | GET | Org-scoped: total_cost, requests, cache_hit_rate, tier hits, avg_quality, etc. **Requires auth.** |
| `/analytics/cost-summary` | GET | Period summary (total_cost, total_requests, cache_hit_rate, avg_quality). **Requires auth.** |
| `/analytics/recent-inferences` | GET | Last N inference events for the org. **Requires auth.** |
| `/analytics/cost-breakdown` | GET | Cost by model/task (org-scoped). **Requires auth.** |
| `/analytics/trends` | GET | Time-series cost/requests/latency (org-scoped). **Requires auth.** |
| `/models` | GET | Registered model profiles and pricing |
| `/auth/signup` | POST | Sign up (email, password, full_name?, org_name?). Returns api_key, user_id, org_id. |
| `/auth/login` | POST | Log in (email, password). Returns api_key, user_id, org_id. |

**Authentication:** Send the API key in the header:

- `Authorization: Bearer <your-api-key>`, or  
- `x-api-key: <your-api-key>`

Metrics and analytics endpoints require a valid key; responses are scoped to the key’s `org_id` (no cross-org data).

**Example — run inference:**

```bash
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_API_KEY" \
  -d '{"prompt": "Summarize this.", "routing_mode": "autopilot"}'
```

---

## Environment Variables

### Backend

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes* | OpenAI API key for inference |
| `ANTHROPIC_API_KEY` | Yes* | Anthropic API key for inference |
| `COHERE_API_KEY` | Yes* | Cohere API key (Tier 2 semantic cache embeddings) |
| `DATABASE_URL` | For signup/auth | PostgreSQL URL. Enables signup, login, and API key storage. |
| `REDIS_URL` | For Tier 1 cache | Redis URL. Fallbacks: `REDIS_PRIVATE_URL`, `REDIS_TLS_URL`, `REDISCLOUD_URL`. |
| `ASAHI_ENCRYPTION_KEY` | Recommended | Passphrase for data-at-rest encryption |
| `ASAHI_AUTH_API_KEY_REQUIRED` | Optional | Set to `true` to require API key on all non-health requests |
| `PORT` | Set by host | Server port (e.g. Railway sets this) |

\*Or use mock mode for local testing without keys.

Optional: `PINECONE_API_KEY` (Tier 2 vector store), `SENDGRID_API_KEY` (welcome email), `TECTON_API_KEY` (feature store).

### Frontend

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Default API base URL (e.g. `https://your-api.railway.app`). Users can override in Settings. |

---

## Configuration

Backend settings live in `config/config.yaml`. Override with environment variables using the `ASAHI_` prefix:

```bash
ASAHI_API_PORT=9000
ASAHI_CACHE_TTL_SECONDS=3600
ASAHI_ROUTING_DEFAULT_QUALITY_THRESHOLD=4.0
ASAHI_GOVERNANCE_AUTH_API_KEY_REQUIRED=true
```

Model profiles (quality score, pricing, latency) are in `config/models.yaml`.

---

## Dashboard Pages

| Route | Description |
|-------|-------------|
| `/` | Landing: hero, features, metrics, CTA |
| `/getting-started` | Get Started: quickstart with **dynamic API base URL** and code example |
| `/signup` | Sign up (email, password, org name) |
| `/login` | Log in |
| `/dashboard` | Metrics: cost savings, requests, total cost, quality; cache hit rate chart; recent inferences |
| `/inference` | Run inference: prompt, routing mode (Autopilot / Guided / Explicit), quality & latency for Guided |
| `/cache` | Cache stats, tier hits, hit rate, storage used, recent cache activity |
| `/analytics` | Cost by model, cost trend, summary (total cost, requests, cache hit rate) |
| `/profile` | Profile and delete account |
| `/settings` | API base URL and API key |

After login, users are redirected to **Get Started**. All dashboard data is org-scoped.

---

## Deployment

- **Backend (Railway):** Add Redis and PostgreSQL; reference `REDIS_URL` and `DATABASE_URL` in the API service. Set LLM and Cohere keys. Use the Procfile or: `uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port $PORT`.
- **Frontend (Vercel):** Set root directory to `frontend`; set `NEXT_PUBLIC_API_URL` to your backend URL.

---

## CLI (Backend)

| Command | Description |
|---------|-------------|
| `python main.py infer --prompt "..."` | Single inference |
| `python main.py test --num_queries 50` | Run test queries |
| `python main.py benchmark` | Baseline vs optimized comparison |
| `python main.py metrics` | View saved metrics |
| `python main.py api [--mock]` | Start REST API (add `--mock` for simulated responses) |

---

## Project Structure

```
asahi/
├── src/
│   ├── config.py           # Settings (YAML + ASAHI_* env overrides)
│   ├── core/optimizer.py   # Orchestrator: cache → route → infer → track
│   ├── models/registry.py  # Model profiles and pricing
│   ├── routing/            # Router, task detector, constraints
│   ├── cache/              # Exact, semantic, intermediate caching
│   ├── embeddings/         # Embedding engine, similarity, vector store
│   ├── tracking/tracker.py # Event logging (in-memory + optional JSONL)
│   ├── observability/      # Metrics, analytics, forecasting, anomaly
│   ├── governance/         # Auth, RBAC, audit, key store (DB)
│   ├── api/app.py          # FastAPI app factory and routes
│   └── api/auth.py         # Auth routes: signup, login, delete-account
├── frontend/               # Next.js dashboard (ACRON UI)
├── config/
│   ├── config.yaml         # Application settings
│   └── models.yaml         # LLM model profiles
├── main.py                 # CLI entry point
├── Procfile                # web: uvicorn for Railway/Heroku
└── requirements.txt
```

---

## Tests

```bash
pytest tests/ -v
pytest tests/ --cov=src --cov-fail-under=90
```

---

## License

MIT
