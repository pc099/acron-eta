# Asahi Production Roadmap

> From working prototype to deployed SaaS.
> Covers packaging, CI/CD, persistence, cloud accounts, backend hosting,
> frontend integration, and the path to Phase 8.
>
> **Current state:** Phases 1-7 code complete, 700+ tests passing, zero
> infrastructure. Everything runs locally with in-memory state.
>
> **Target state:** Dockerised backend on a cloud VM, GitHub Actions CI/CD,
> PostgreSQL + Redis + Pinecone persistence, ready for a React dashboard.

---

## Table of Contents

1. [Accounts and Services to Set Up](#1-accounts-and-services-to-set-up)
2. [Where the Backend Runs](#2-where-the-backend-runs)
3. [Step A: Project Packaging](#step-a-project-packaging)
4. [Step B: Docker and Local Compose](#step-b-docker-and-local-compose)
5. [Step C: GitHub Actions CI/CD](#step-c-github-actions-cicd)
6. [Step D: Async LLM Calls](#step-d-async-llm-calls)
7. [Step E: PostgreSQL Persistence](#step-e-postgresql-persistence)
8. [Step F: Redis Integration](#step-f-redis-integration)
9. [Step G: Pinecone Vector DB](#step-g-pinecone-vector-db)
10. [Step H: Cloud Deployment](#step-h-cloud-deployment)
11. [Step I: Observability Stack](#step-i-observability-stack)
12. [Step J: Frontend Dashboard](#step-j-frontend-dashboard)
13. [Step K: Hardening and Phase 8](#step-k-hardening-and-phase-8)
14. [Dependency Graph](#dependency-graph)
15. [Cost Estimates](#cost-estimates)

---

## 1. Accounts and Services to Set Up

Create these accounts **before starting implementation**. All have free tiers
sufficient for development and staging.

### 1.1 Required Accounts

| Service | Purpose | Free Tier | Sign-Up URL | What You Need |
|---------|---------|-----------|-------------|---------------|
| **GitHub** | Code hosting, CI/CD (Actions) | 2,000 min/month Actions | github.com | Already have (repo exists) |
| **Docker Hub** | Container image registry | 1 private repo, unlimited public | hub.docker.com | Account + access token |
| **Pinecone** | Vector database (semantic cache) | 1 index, 100K vectors | pinecone.io | **Already set up** (Chaitanya varma's Org). Create an index named `asahi-vectors`, dimension=1024, metric=cosine |
| **Anthropic** | Claude API | Pay-as-you-go | console.anthropic.com | API key (already have) |
| **OpenAI** | GPT API | Pay-as-you-go | platform.openai.com | API key |
| **Cohere** | Embedding API (embed-english-v3.0) | 1,000 calls/month free | dashboard.cohere.com | API key |

### 1.2 Cloud Provider (Pick One)

You need a cloud provider to host the backend. Here are the options ranked by
cost for a single-developer project:

| Provider | Service | Monthly Cost (Dev) | Best For |
|----------|---------|-------------------|----------|
| **Railway** | Managed containers | $5-20 | Simplest. Deploy from GitHub in 2 clicks. Postgres + Redis add-ons built in |
| **Render** | Web service + managed DBs | $7-25 | Good free tier for web services. Managed Postgres $7/mo |
| **DigitalOcean** | Droplet + managed DB | $12-30 | More control. $6 droplet + $15 managed Postgres |
| **AWS (Lightsail)** | Container + RDS | $15-40 | AWS ecosystem. Lightsail is the simple entry point |
| **Fly.io** | Edge containers | $5-15 | Great CLI. Free allowance for small apps |

**Recommendation for solo dev: Railway or Render.** Both deploy directly from
GitHub, include managed Postgres and Redis, and cost under $25/month.

### 1.3 Optional Accounts (For Later)

| Service | Purpose | When Needed |
|---------|---------|-------------|
| **Sentry** | Error tracking | Step I (Observability) |
| **Grafana Cloud** | Dashboards + Prometheus | Step I (free tier: 10K metrics) |
| **Vercel** | Frontend hosting (React dashboard) | Step J (Frontend) |
| **Upstash** | Serverless Redis (alternative) | Step F if not using Railway/Render built-in |

### 1.4 GitHub Repository Secrets

Once you pick a cloud provider, add these secrets to your GitHub repo
(`Settings > Secrets and variables > Actions`):

```
# LLM Provider Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
COHERE_API_KEY=...

# Pinecone
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=...     # e.g. us-east-1

# Infrastructure
DATABASE_URL=postgresql://...  # from your managed Postgres
REDIS_URL=redis://...          # from your managed Redis

# Governance
ASAHI_ENCRYPTION_KEY=...       # generate: python -c "import secrets; print(secrets.token_hex(32))"

# Docker Registry
DOCKERHUB_USERNAME=...
DOCKERHUB_TOKEN=...

# Cloud Deploy (depends on provider)
RAILWAY_TOKEN=...              # if Railway
RENDER_API_KEY=...             # if Render
```

---

## 2. Where the Backend Runs

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                         INTERNET                                │
│                            │                                    │
│                    ┌───────┴───────┐                            │
│                    │  Cloud Host   │  Railway / Render /        │
│                    │  (Container)  │  DigitalOcean              │
│                    │               │                            │
│                    │  FastAPI +    │  Port 8000                 │
│                    │  Uvicorn      │  TLS via provider          │
│                    └───┬───┬───┬───┘                            │
│                        │   │   │                                │
│           ┌────────────┘   │   └────────────┐                  │
│           │                │                │                  │
│    ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐          │
│    │  PostgreSQL │  │    Redis    │  │  Pinecone   │          │
│    │  (Managed)  │  │  (Managed)  │  │  (Cloud)    │          │
│    │             │  │             │  │             │          │
│    │ • Events    │  │ • Cache L1  │  │ • Vectors   │          │
│    │ • API keys  │  │ • Rate lim  │  │ • Semantic  │          │
│    │ • Audit log │  │ • Sessions  │  │   cache     │          │
│    │ • Policies  │  │             │  │             │          │
│    └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                                 │
│    ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│    │ Anthropic   │  │  OpenAI     │  │  Cohere     │          │
│    │ Claude API  │  │  GPT API   │  │ Embed API   │          │
│    └─────────────┘  └─────────────┘  └─────────────┘          │
│                                                                 │
│  ┌──────────────────────────────────────────────────┐          │
│  │              FRONTEND (Later)                     │          │
│  │  React/Next.js on Vercel                          │          │
│  │  Calls Asahi API via HTTPS                        │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
User/Frontend
    │
    ▼
FastAPI (Asahi)
    │
    ├── Check Redis cache (L1 exact match)
    │      HIT → return cached response (0ms LLM cost)
    │
    ├── Check Pinecone (L2 semantic match)
    │      HIT → return similar cached response
    │
    ├── Route to LLM provider (Anthropic/OpenAI)
    │      Execute inference
    │
    ├── Store result in Redis + Pinecone
    │
    ├── Log event to PostgreSQL
    │
    └── Return response
```

### 2.3 Frontend Considerations

The dashboard will be a **separate React/Next.js app** that calls the Asahi
API. Complete wireframes and a design system are in:
- `docs/ASAHI_FRONTEND_WIREFRAMES.md` -- ASCII wireframes for 7 pages + mobile
- `docs/ASAHI_FRONTEND_DESIGN_SYSTEM.md` -- React components, Tailwind config, color system

The backend API already exposes all the endpoints the dashboard needs:

| Dashboard Section | Backend Endpoint | Data |
|-------------------|-----------------|------|
| Cost Overview | `GET /metrics` | Total cost, savings, requests |
| Model Usage | `GET /models` | Model profiles, pricing |
| Cost Breakdown | `GET /analytics/cost-breakdown` | By model, task, period |
| Trends | `GET /analytics/trends` | Time-series cost/latency |
| Forecasting | `GET /analytics/forecast` | Predicted spend |
| Anomalies | `GET /analytics/anomalies` | Active alerts |
| Recommendations | `GET /analytics/recommendations` | Optimisation suggestions |
| Cache Performance | `GET /analytics/cache-performance` | Per-tier hit rates |
| Latency | `GET /analytics/latency-percentiles` | p50/p75/p90/p95/p99 |
| Inference | `POST /infer` | Run queries from playground |
| Governance | `GET /governance/audit` | Audit log viewer |
| API Keys | `POST /governance/api-keys` | Key management |
| Policies | `GET/POST /governance/policies/{org}` | Policy CRUD |
| Health | `GET /health` | System status |
| Cache Mgmt (new) | `DELETE /cache/clear`, `GET /cache/export` | Clear/export cache |

Frontend deployment is **Step J** and is independent of backend work.

---

## Step A: Project Packaging

**Goal:** Proper Python packaging with `pyproject.toml` so the project can be
installed, built, and dependencies are locked.

### A.1 Create `pyproject.toml`

Replace `requirements.txt` with a proper `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68.0", "wheel"]
build-backend = "setuptools.backends._legacy:_Backend"

[project]
name = "asahi"
version = "1.0.0"
description = "LLM Inference Cost Optimizer"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.6.0",
    "anthropic>=0.40.0",
    "openai>=1.55.0",
    "python-dotenv>=1.0.0",
    "pyyaml>=6.0.2",
    "httpx>=0.27.0",
    "numpy>=1.26.0",
    "cryptography>=43.0.0",
    "bcrypt>=4.2.0",
    "gunicorn>=22.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-cov>=6.0.0",
    "pytest-asyncio>=0.24.0",
    "black>=24.10.0",
    "ruff>=0.8.0",
    "mypy>=1.13.0",
]
kafka = [
    "kafka-python>=2.0.2",
]
db = [
    "sqlalchemy>=2.0.0",
    "alembic>=1.13.0",
    "asyncpg>=0.29.0",
    "psycopg2-binary>=2.9.0",
    "redis>=5.0.0",
    "pinecone-client>=3.0.0",
]
```

### A.2 Create `.gitignore` Updates

Ensure these are present:

```
.env
*.pyc
__pycache__/
.pytest_cache/
.mypy_cache/
dist/
build/
*.egg-info/
data/logs/
data/audit/
asahi.db
```

### A.3 Generate Lock File

```bash
pip install pip-tools
pip-compile pyproject.toml -o requirements.lock
```

### A.4 Verification

- [ ] `pip install -e ".[dev,db]"` succeeds
- [ ] `pytest tests/ -v` still passes (700+ tests)
- [ ] `python main.py benchmark --mock` works

---

## Step B: Docker and Local Compose

**Goal:** Containerise the app and run the full stack locally with
`docker compose up`.

### B.1 Create `Dockerfile`

```dockerfile
# ── Stage 1: Builder ──
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml requirements.lock ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock

# ── Stage 2: Runtime ──
FROM python:3.12-slim AS runtime
WORKDIR /app

RUN groupadd -r asahi && useradd -r -g asahi asahi

COPY --from=builder /install /usr/local
COPY src/ src/
COPY config/ config/
COPY main.py .

# Create data directories
RUN mkdir -p data/logs data/audit && chown -R asahi:asahi data/

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

USER asahi
EXPOSE 8000

CMD ["gunicorn", "src.api.app:create_app()", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--timeout", "120"]
```

### B.2 Create `docker-compose.yml`

```yaml
services:
  asahi:
    build: .
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - DATABASE_URL=postgresql://asahi:asahi@postgres:5432/asahi
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: asahi
      POSTGRES_PASSWORD: asahi
      POSTGRES_DB: asahi
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U asahi"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

volumes:
  pgdata:
```

### B.3 Create `.dockerignore`

```
.git
.venv
asahi/
__pycache__
*.pyc
.pytest_cache
.mypy_cache
data/logs/
data/audit/
tests/
docs/
.env
*.md
```

### B.4 Verification

- [ ] `docker compose build` succeeds
- [ ] `docker compose up` starts all 3 services
- [ ] `curl http://localhost:8000/health` returns healthy
- [ ] `curl -X POST http://localhost:8000/infer -H 'Content-Type: application/json' -d '{"prompt":"test"}'` works (mock mode)

---

## Step C: GitHub Actions CI/CD

**Goal:** Automated testing on every push, Docker build on merge to main,
deploy to cloud on release.

### C.1 CI Pipeline: `.github/workflows/ci.yml`

Runs on every push and pull request.

```yaml
name: CI

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install black ruff mypy
      - run: black --check src/ tests/
      - run: ruff check src/

  test:
    runs-on: ubuntu-latest
    needs: lint
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --tb=short -q
        env:
          ANTHROPIC_API_KEY: "sk-test-fake"

  docker-build:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: |
            ${{ secrets.DOCKERHUB_USERNAME }}/asahi:latest
            ${{ secrets.DOCKERHUB_USERNAME }}/asahi:${{ github.sha }}
```

### C.2 Deploy Pipeline: `.github/workflows/deploy.yml`

Deploys to cloud on push to main (after CI passes).

```yaml
name: Deploy

on:
  workflow_run:
    workflows: [CI]
    types: [completed]
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v4

      # ── Option A: Railway ──
      - name: Deploy to Railway
        uses: bervProject/railway-deploy@main
        with:
          railway_token: ${{ secrets.RAILWAY_TOKEN }}
          service: asahi-api

      # ── Option B: Render (use webhook) ──
      # - name: Deploy to Render
      #   run: curl -X POST ${{ secrets.RENDER_DEPLOY_HOOK_URL }}

      # ── Smoke test ──
      - name: Smoke test
        run: |
          sleep 30
          curl -f https://your-app-url.up.railway.app/health
```

### C.3 Branch Strategy

```
main          ─────●─────●─────●─────●───── (production deploys)
                   │           │
staging       ─────●───●───●───●───────────── (staging deploys)
                   │   │
feat/xyz      ─────●───●───────────────────── (CI only, no deploy)
```

| Branch | CI | Docker Build | Deploy |
|--------|------|------------|--------|
| `feat/*` or PR | Lint + Test | No | No |
| `staging` | Lint + Test | Yes | Staging (auto) |
| `main` | Lint + Test | Yes | Production (auto after CI) |

### C.4 Verification

- [ ] Push to a `feat/` branch triggers lint + test
- [ ] Merge to `main` triggers Docker build + push
- [ ] Deploy workflow runs after successful CI on main
- [ ] Smoke test hits the deployed `/health` endpoint

---

## Step D: Async LLM Calls

**Goal:** Make LLM provider calls non-blocking so FastAPI can handle concurrent
requests.

### D.1 What Changes

| File | Change |
|------|--------|
| `src/core/optimizer.py` | Replace `openai.OpenAI` and `anthropic.Anthropic` with async clients. Add `async def _call_openai_async()` and `async def _call_anthropic_async()` |
| `src/core/optimizer.py` | Make `infer()` method sync wrapper around async internals using `asyncio.run()` or keep sync for CLI, add `async_infer()` for API |
| `src/api/app.py` | Call `optimizer.async_infer()` from async endpoint handlers |
| `requirements.txt` | Already has `httpx>=0.27.0` (good) |

### D.2 Approach

```python
# src/core/optimizer.py -- new async methods

async def _call_openai_async(self, model_name: str, prompt: str):
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = await client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
    )
    # ... same parsing logic

async def _call_anthropic_async(self, model_name: str, prompt: str):
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = await client.messages.create(
        model=model_name,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    # ... same parsing logic
```

### D.3 Why This Matters

Currently, when the API receives a request, the LLM call **blocks the entire
event loop**. With 4 Gunicorn workers, only 4 requests can be in-flight. With
async calls, each worker can handle hundreds of concurrent requests while
waiting for LLM responses (which take 150-2000ms).

### D.4 Verification

- [ ] `POST /infer` works with real API keys (non-mock)
- [ ] Multiple concurrent requests don't block each other
- [ ] Mock mode still works (sync is fine for mocks)
- [ ] All existing tests pass

---

## Step E: PostgreSQL Persistence

**Goal:** Persist events, API keys, audit logs, and governance policies to
PostgreSQL so they survive restarts.

### E.1 New Dependencies

```
sqlalchemy>=2.0.0
alembic>=1.13.0
psycopg2-binary>=2.9.0   # sync driver
asyncpg>=0.29.0           # async driver (for future)
```

### E.2 New File: `src/db.py`

Database engine, session factory, and base model.

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

class Base(DeclarativeBase):
    pass

def get_engine(database_url: str):
    return create_engine(database_url, pool_pre_ping=True, pool_size=10)

def get_session_factory(engine):
    return sessionmaker(bind=engine)
```

### E.3 Database Tables

| Table | Purpose | Source Module |
|-------|---------|---------------|
| `inference_events` | Every inference request log | `src/tracking/tracker.py` |
| `api_keys` | Hashed API keys with metadata | `src/governance/auth.py` |
| `audit_entries` | Tamper-evident audit log | `src/governance/audit.py` |
| `org_policies` | Per-org governance policies | `src/governance/rbac.py` |
| `compliance_profiles` | Per-org compliance config | `src/governance/compliance.py` |
| `tenants` | Tenant/org registry | `src/governance/tenancy.py` |

### E.4 Schema: `inference_events`

```sql
CREATE TABLE inference_events (
    id              BIGSERIAL PRIMARY KEY,
    request_id      VARCHAR(24) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id         VARCHAR(255),
    org_id          VARCHAR(255),
    task_type       VARCHAR(100),
    model_selected  VARCHAR(100) NOT NULL,
    cache_hit       BOOLEAN NOT NULL DEFAULT FALSE,
    cache_tier      SMALLINT DEFAULT 0,
    input_tokens    INTEGER NOT NULL DEFAULT 0,
    output_tokens   INTEGER NOT NULL DEFAULT 0,
    total_tokens    INTEGER NOT NULL DEFAULT 0,
    latency_ms      INTEGER NOT NULL DEFAULT 0,
    cost            NUMERIC(10,6) NOT NULL DEFAULT 0,
    routing_reason  TEXT,
    quality_score   NUMERIC(4,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_events_timestamp ON inference_events(timestamp);
CREATE INDEX idx_events_org_id ON inference_events(org_id);
CREATE INDEX idx_events_model ON inference_events(model_selected);
```

### E.5 Schema: `api_keys`

```sql
CREATE TABLE api_keys (
    id              BIGSERIAL PRIMARY KEY,
    key_prefix      VARCHAR(12) UNIQUE NOT NULL,
    key_hash        VARCHAR(255) NOT NULL,
    user_id         VARCHAR(255) NOT NULL,
    org_id          VARCHAR(255) NOT NULL,
    scopes          JSONB DEFAULT '[]',
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked         BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### E.6 Schema: `audit_entries`

```sql
CREATE TABLE audit_entries (
    id                  BIGSERIAL PRIMARY KEY,
    entry_id            VARCHAR(32) UNIQUE NOT NULL,
    timestamp           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    org_id              VARCHAR(255) NOT NULL,
    user_id             VARCHAR(255) NOT NULL,
    action              VARCHAR(100) NOT NULL,
    resource            VARCHAR(255) NOT NULL,
    details             JSONB DEFAULT '{}',
    ip_address          VARCHAR(45),
    user_agent          TEXT,
    result              VARCHAR(20) NOT NULL DEFAULT 'success',
    data_classification VARCHAR(20) NOT NULL DEFAULT 'internal',
    prev_hash           VARCHAR(64)
);

CREATE INDEX idx_audit_org_id ON audit_entries(org_id);
CREATE INDEX idx_audit_timestamp ON audit_entries(timestamp);
```

### E.7 Alembic Setup

```bash
cd d:/claude/asahi
pip install alembic sqlalchemy psycopg2-binary
alembic init alembic
# Edit alembic.ini: sqlalchemy.url = postgresql://asahi:asahi@localhost:5432/asahi
# Edit alembic/env.py to import Base from src.db
alembic revision --autogenerate -m "initial tables"
alembic upgrade head
```

### E.8 Migration Strategy

- All schema changes go through Alembic migration scripts
- Migrations run at container startup (entrypoint script)
- Backward-compatible only (add columns, don't rename/drop)
- Test migrations in CI against a fresh Postgres container

### E.9 Module Wiring

Each module gets a `*Repository` class that wraps SQLAlchemy operations:

| Module | Repository | Methods |
|--------|-----------|---------|
| `src/tracking/tracker.py` | `EventRepository` | `save_event()`, `query_events()` |
| `src/governance/auth.py` | `ApiKeyRepository` | `store_key()`, `get_key()`, `revoke_key()` |
| `src/governance/audit.py` | `AuditRepository` | `append()`, `query()`, `verify_chain()` |
| `src/governance/rbac.py` | `PolicyRepository` | `save_policy()`, `get_policy()` |
| `src/governance/tenancy.py` | `TenantRepository` | `create()`, `get()`, `list()` |

The existing in-memory implementations remain as **fallbacks** when no
`DATABASE_URL` is configured (local development without Docker).

### E.10 Verification

- [ ] `alembic upgrade head` creates all tables
- [ ] `alembic downgrade -1` then `upgrade head` is idempotent
- [ ] Events persist across container restarts
- [ ] API keys survive restarts
- [ ] Audit log chain integrity verified after restart
- [ ] All existing tests pass (in-memory fallback)

---

## Step F: Redis Integration

**Goal:** Move exact-match cache and rate limiting from in-memory dicts to
Redis for persistence and multi-worker consistency.

### F.1 New Dependency

```
redis>=5.0.0
```

### F.2 New File: `src/cache/redis_backend.py`

```python
import redis
import json
from typing import Optional

class RedisCache:
    """Redis-backed exact-match cache (replaces in-memory dict)."""

    def __init__(self, redis_url: str, ttl_seconds: int = 86400):
        self._client = redis.from_url(redis_url, decode_responses=True)
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[dict]:
        data = self._client.get(f"cache:{key}")
        return json.loads(data) if data else None

    def set(self, key: str, value: dict) -> None:
        self._client.setex(f"cache:{key}", self._ttl, json.dumps(value))

    def delete(self, key: str) -> bool:
        return self._client.delete(f"cache:{key}") > 0

    def clear(self) -> int:
        keys = self._client.keys("cache:*")
        return self._client.delete(*keys) if keys else 0
```

### F.3 Redis Rate Limiter

Replace the in-memory sliding window with Redis-backed rate limiting:

```python
class RedisRateLimiter:
    """Distributed rate limiter using Redis sorted sets."""

    def __init__(self, redis_url: str, max_requests: int, window_seconds: int):
        self._client = redis.from_url(redis_url)
        self._max = max_requests
        self._window = window_seconds

    def is_allowed(self, client_id: str) -> bool:
        # Use Redis sorted set with timestamp scores
        # ZADD + ZREMRANGEBYSCORE + ZCARD pattern
        ...
```

### F.4 Config Integration

Add to `src/config.py`:

```python
@dataclass
class RedisSettings:
    url: str = "redis://localhost:6379/0"
    cache_prefix: str = "asahi:cache"
    rate_limit_prefix: str = "asahi:rl"
```

The app auto-detects Redis: if `REDIS_URL` is set, use Redis backend.
Otherwise, fall back to in-memory (for local development without Docker).

### F.5 Verification

- [ ] Cache hits work across multiple Gunicorn workers
- [ ] Rate limiting is consistent across workers
- [ ] Cache entries persist across container restarts
- [ ] Fallback to in-memory when Redis is unavailable
- [ ] All existing tests pass

---

## Step G: Pinecone Vector DB

**Goal:** Move semantic cache vectors from in-memory NumPy arrays to Pinecone
for persistence and scalability.

### G.1 Pinecone Account Setup

You already have a Pinecone account (Chaitanya varma's Org). Steps:

1. Go to **Database > Indexes > Create Index**
2. Name: `asahi-vectors`
3. Dimensions: `1024` (matches Cohere embed-english-v3.0)
4. Metric: `cosine`
5. Spec: **Serverless** (free tier, us-east-1)
6. Copy the API key from **API Keys** page

### G.2 New Dependency

```
pinecone-client>=3.0.0
```

### G.3 New File: `src/cache/pinecone_backend.py`

```python
from pinecone import Pinecone

class PineconeVectorStore:
    """Pinecone-backed vector store for semantic caching."""

    def __init__(self, api_key: str, index_name: str = "asahi-vectors"):
        self._pc = Pinecone(api_key=api_key)
        self._index = self._pc.Index(index_name)

    def upsert(self, id: str, vector: list, metadata: dict) -> None:
        self._index.upsert(vectors=[{
            "id": id,
            "values": vector,
            "metadata": metadata,
        }])

    def query(self, vector: list, top_k: int = 5) -> list:
        results = self._index.query(vector=vector, top_k=top_k, include_metadata=True)
        return results.matches

    def delete(self, ids: list) -> None:
        self._index.delete(ids=ids)
```

### G.4 Integration with Semantic Cache

Wire `PineconeVectorStore` into `src/cache/semantic.py` as an alternative to
the in-memory `VectorDatabase`. The existing `VectorDatabase` in
`src/embeddings/vector_store.py` becomes the local-dev fallback.

### G.5 Config

```yaml
# config/config.yaml
vector_db:
  provider: pinecone        # pinecone | local
  index_name: asahi-vectors
  api_key_env: PINECONE_API_KEY
```

### G.6 Verification

- [ ] Vectors persist in Pinecone after container restart
- [ ] Semantic cache queries return correct similar results
- [ ] Upsert + query round-trip < 100ms
- [ ] Fallback to in-memory when Pinecone is unavailable
- [ ] All existing tests pass (mock/local backend)

---

## Step H: Cloud Deployment

**Goal:** Deploy the Dockerised app to a cloud provider with managed Postgres
and Redis.

### H.1 Option A: Railway (Recommended for Solo Dev)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Create project
railway init

# Add PostgreSQL
railway add --plugin postgresql

# Add Redis
railway add --plugin redis

# Set environment variables
railway variables set ANTHROPIC_API_KEY=sk-ant-...
railway variables set OPENAI_API_KEY=sk-...
railway variables set COHERE_API_KEY=...
railway variables set PINECONE_API_KEY=...
railway variables set ASAHI_ENCRYPTION_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# Deploy
railway up
```

Railway auto-injects `DATABASE_URL` and `REDIS_URL` from the plugins.

**Cost:** ~$5-20/month on the Hobby plan.

### H.2 Option B: Render

1. Go to render.com, connect your GitHub repo
2. Create a **Web Service** (Docker, auto-deploy from main)
3. Create a **PostgreSQL** instance ($7/month)
4. Create a **Redis** instance ($10/month free tier available)
5. Add env vars in the dashboard
6. Render auto-deploys on push to main

### H.3 Option C: DigitalOcean

1. Create a $6/month Droplet (1 vCPU, 1GB RAM)
2. Install Docker on the Droplet
3. Create a managed PostgreSQL cluster ($15/month)
4. Create a managed Redis cluster ($15/month)
5. Use GitHub Actions to SSH-deploy or use DigitalOcean App Platform

### H.4 DNS and TLS

All three providers offer:
- Free TLS certificates (Let's Encrypt)
- Custom domain support
- Automatic HTTPS

Point your domain (e.g. `api.asahi.dev`) to the provider's URL.

### H.5 Verification

- [ ] `https://your-domain/health` returns healthy with correct version
- [ ] `POST /infer` works with real API keys
- [ ] Events persist in Postgres
- [ ] Cache works via Redis
- [ ] GitHub push triggers auto-deploy
- [ ] TLS certificate valid

---

## Step I: Observability Stack

**Goal:** Set up real monitoring, error tracking, and dashboards.

### I.1 Grafana Cloud (Free Tier)

1. Sign up at grafana.com (free: 10K metrics, 50GB logs, 50GB traces)
2. Get your Prometheus remote write URL and API key
3. Add `prometheus-client` to the app
4. Configure remote write in the app or use Grafana Agent sidecar

### I.2 Sentry (Error Tracking)

```bash
pip install sentry-sdk[fastapi]
```

```python
# src/api/app.py
import sentry_sdk
sentry_sdk.init(dsn=os.getenv("SENTRY_DSN"), traces_sample_rate=0.1)
```

### I.3 Structured Logging

```bash
pip install python-json-logger
```

Configure all loggers to output JSON so cloud log aggregators can parse them.

### I.4 Health Check Depth

Enhance `/health` to check all dependencies:

```json
{
    "status": "healthy",
    "version": "1.0.0",
    "components": {
        "postgres": "healthy",
        "redis": "healthy",
        "pinecone": "healthy",
        "anthropic": "reachable",
        "openai": "reachable"
    }
}
```

### I.5 Dashboards

Import Grafana dashboards that visualize:
- Request rate and error rate
- Cost per hour / day
- Latency percentiles (p50, p95, p99)
- Cache hit rate by tier
- Model usage distribution

The Asahi code already generates Prometheus-format metrics at
`GET /analytics/prometheus`.

### I.6 Verification

- [ ] Grafana dashboard shows live metrics
- [ ] Sentry captures exceptions with stack traces
- [ ] Logs are structured JSON
- [ ] `/health` checks all dependencies

---

## Step J: Frontend Dashboard

**Goal:** Build a React dashboard that consumes the Asahi API. Wireframes and
design system are already defined in `docs/ASAHI_FRONTEND_WIREFRAMES.md` and
`docs/ASAHI_FRONTEND_DESIGN_SYSTEM.md`.

### J.1 Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Framework | Next.js 14+ (App Router) | SSR, file-based routing, API routes |
| UI | Tailwind CSS + shadcn/ui + heroicons | Fast, consistent styling (Asahi orange #FF6B35) |
| Charts | Recharts | Cost/latency/cache visualisations (matches design system) |
| State | React Query (TanStack) | Cache + auto-refresh API data |
| Auth | NextAuth.js | User login, session management |
| Hosting | Vercel | Free tier, auto-deploy from GitHub |

> **Note:** The design system doc (`ASAHI_FRONTEND_DESIGN_SYSTEM.md`) uses
> `.jsx` files and the Pages Router pattern. When implementing, use `.tsx` with
> TypeScript throughout and the App Router (`app/` directory). The design system
> components are reference implementations for styling/layout, not the final
> file structure.

### J.2 Pages

The frontend has two zones: a public landing page and an authenticated dashboard.

```
app/
├── page.tsx                       # Landing/marketing page (public, see Wireframes §1)
├── login/page.tsx                 # Login page
├── dashboard/
│   └── page.tsx                   # Dashboard overview (Wireframes §2)
├── inference/page.tsx             # Inference testing playground (Wireframes §3)
├── cache/page.tsx                 # Cache management with tier stats (Wireframes §4)
├── analytics/
│   ├── page.tsx                   # Analytics overview (Wireframes §5)
│   ├── cost/page.tsx              # Cost breakdown (GET /analytics/cost-breakdown)
│   ├── trends/page.tsx            # Time-series trends (GET /analytics/trends)
│   └── forecast/page.tsx          # Cost forecasting (GET /analytics/forecast)
├── models/page.tsx                # Model registry (GET /models)
├── governance/
│   ├── audit/page.tsx             # Audit log (GET /governance/audit)
│   ├── keys/page.tsx              # API key management (POST /governance/api-keys)
│   └── policies/page.tsx          # Policy CRUD (GET/POST /governance/policies/{org})
├── alerts/page.tsx                # Anomalies + recommendations
└── settings/page.tsx              # General, Cache, Routing config (Wireframes §6)
```

**Page-to-wireframe mapping:**

| Page | Wireframe Section | Backend Endpoints |
|------|------------------|-------------------|
| Landing | §1 Landing Page | None (static) |
| Dashboard | §2 Dashboard | `GET /metrics`, `GET /analytics/cache-performance` |
| Inference | §3 Inference Page | `POST /infer` |
| Cache | §4 Cache Management | `GET /analytics/cache-performance`, `DELETE /cache` (new) |
| Analytics | §5 Analytics Page | `GET /analytics/cost-breakdown`, `/trends`, `/forecast`, `/latency-percentiles` |
| Settings | §6 Settings Page | `GET /models`, `POST /governance/api-keys` |
| Governance | No wireframe yet | `GET /governance/audit`, `/policies/{org}` |
| Alerts | No wireframe yet | `GET /analytics/anomalies`, `/recommendations` |

> **TODO:** Create wireframes for the Governance and Alerts pages before
> implementing them. These pages exist in the roadmap because the backend
> endpoints are ready, but they have no visual design yet.

### J.3 Sidebar Navigation

Combines the wireframe sidebar (§2-§6) with additional backend-driven pages:

```
┌──────────────────┐
│  Dashboard        │  ← Overview metrics cards + charts
│  Inference        │  ← Prompt playground with routing modes
│  Cache            │  ← Per-tier stats (T1/T2/T3), clear/export controls
│  Analytics        │
│    ├─ Cost        │
│    ├─ Trends      │
│    └─ Forecast    │
│  Models           │  ← Model registry with pricing
│  Governance       │
│    ├─ Audit Log   │
│    ├─ API Keys    │
│    └─ Policies    │
│  Alerts           │  ← Anomalies + recommendations
│  Settings         │  ← General, Cache config, Routing config
└──────────────────┘
```

The sidebar collapses to a hamburger menu on mobile (320px+). See
Wireframes §7 for the mobile layout.

### J.4 Backend Endpoints Needed (New)

The wireframes define cache management controls (Clear All, Clear Expired,
Export Data) that require backend endpoints not yet built:

| Method | Path | Purpose | Status |
|--------|------|---------|--------|
| DELETE | `/cache/clear` | Clear all cache entries | **New -- build before frontend** |
| DELETE | `/cache/expired` | Clear expired entries only | **New -- build before frontend** |
| GET | `/cache/export` | Export cache entries as JSON | **New -- build before frontend** |

### J.5 API Connection

The frontend calls the Asahi backend via `NEXT_PUBLIC_API_URL`:

```typescript
// lib/api.ts
const API = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function getMetrics() {
    const res = await fetch(`${API}/metrics`);
    return res.json();
}

export async function runInference(prompt: string, options: InferOptions) {
    const res = await fetch(`${API}/infer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, ...options }),
    });
    return res.json();
}

export async function getCostBreakdown(period: string, groupBy: string) {
    const res = await fetch(`${API}/analytics/cost-breakdown?period=${period}&group_by=${groupBy}`);
    return res.json();
}

export async function getCachePerformance() {
    const res = await fetch(`${API}/analytics/cache-performance`);
    return res.json();
}
```

### J.6 CORS Configuration

The backend already supports CORS via `settings.api.cors_origins`. For
production, set this to the Vercel domain:

```yaml
# config/config.yaml
api:
  cors_origins:
    - "https://asahi-dashboard.vercel.app"
    - "http://localhost:3000"  # local dev
```

### J.7 Design References

| Document | Contents |
|----------|----------|
| `docs/ASAHI_FRONTEND_WIREFRAMES.md` | ASCII wireframes for all pages, color palette, typography, spacing grid, component states |
| `docs/ASAHI_FRONTEND_DESIGN_SYSTEM.md` | React component implementations (Button, Card, Sidebar, etc.), Tailwind config, project structure |

Key design tokens from the wireframes:
- Primary: `#FF6B35` (Asahi Orange), Light: `#FFB84D`, Very Light: `#FFF3E0`
- Font: Inter, 8px spacing grid, sidebar width 256px
- Charts: Line charts for trends, pie charts for model distribution, bar charts for tier breakdown

### J.8 Verification

- [ ] Landing page renders with hero, features, metrics, CTA sections
- [ ] Dashboard loads and shows live data from backend (4 metric cards + 2 charts)
- [ ] Inference page sends requests with routing mode selector and shows results
- [ ] Cache management shows per-tier stats (Tier 1/2/3) and controls work
- [ ] Analytics pages render charts with real data
- [ ] Governance pages show audit logs, API keys, and policies
- [ ] Settings page tabs (General, API Keys, Cache, Routing) work
- [ ] Responsive layout works on mobile (320px+, hamburger sidebar)
- [ ] CORS works in production (Vercel to Railway/Render)

---

## Step K: Hardening and Phase 8

After the baseline is stable, these are the next priorities:

### K.1 Reliability Hardening

| Task | Description |
|------|-------------|
| Circuit breakers | If a provider fails 3x in a row, stop calling it for 60s |
| Graceful shutdown | Handle SIGTERM, drain in-flight requests |
| Connection pooling | SQLAlchemy pool for Postgres, connection pool for Redis |
| Request timeouts | Enforce timeout on all LLM calls (configurable, default 30s) |
| Retry with backoff | Exponential backoff with jitter on provider 5xx errors |

### K.2 Security Hardening

| Task | Description |
|------|-------------|
| Secrets rotation | Support key rotation without downtime |
| Input sanitization | Limit prompt length, reject injection patterns |
| HTTPS enforcement | Redirect HTTP to HTTPS, HSTS headers |
| Dependency scanning | Add `pip-audit` to CI pipeline |
| Container scanning | Add `trivy` to CI pipeline |

### K.3 Performance Testing

| Task | Tool | Goal |
|------|------|------|
| Load test | Locust or k6 | 100 concurrent users, <500ms p95 |
| Stress test | k6 | Find breaking point |
| Soak test | k6 (8-hour run) | No memory leaks |

### K.4 Phase 8: Agent Swarm (Future)

Prerequisite: Steps A-H complete (persistent storage, async calls, CI/CD).

See `docs/phase8_requirements.md` for full spec. Key components:
- Agent contextual cache (shares context across agent calls)
- Inter-agent message compression
- Agent state management (persisted to Postgres)
- Specialisation router
- Cost attribution per agent
- Failure recovery

---

## Dependency Graph

```
Step A: Packaging
    │
    ├── Step B: Docker ──────────────┐
    │       │                        │
    │       ├── Step C: CI/CD        │
    │       │                        │
    │       └── Step H: Cloud Deploy─┤
    │                                │
    ├── Step D: Async LLM ───────────┤
    │                                │
    ├── Step E: PostgreSQL ──────────┤  (needs Docker for local Postgres)
    │                                │
    ├── Step F: Redis ───────────────┤  (needs Docker for local Redis)
    │                                │
    └── Step G: Pinecone ────────────┘  (cloud-only, no Docker needed)

Step I: Observability  (after H)
Step J: Frontend       (after H, independent of I)
Step K: Hardening      (after I + J)
Phase 8: Agent Swarm   (after K)
```

**Parallelisation:** Steps D, E, F, G can be worked on in parallel once B
is done. Step C can be done right after A (doesn't need B).

**Recommended order:**
1. A → B → C (packaging + Docker + CI) — **do first, 1-2 sessions**
2. D (async) — **next, 1 session**
3. E + F in parallel (Postgres + Redis) — **2-3 sessions**
4. G (Pinecone) — **1 session**
5. H (cloud deploy) — **1 session**
6. I (observability) — **1 session**
7. J (frontend) — **2-3 sessions**
8. K + Phase 8 — **ongoing**

---

## Cost Estimates

### Monthly Running Costs (Development/Staging)

| Service | Provider | Cost |
|---------|----------|------|
| Backend hosting | Railway Hobby | $5 |
| PostgreSQL | Railway add-on | $5 |
| Redis | Railway add-on | $5 |
| Pinecone | Free tier | $0 |
| Docker Hub | Free (public) | $0 |
| GitHub Actions | Free (2000 min) | $0 |
| Grafana Cloud | Free tier | $0 |
| Sentry | Free tier | $0 |
| Vercel (frontend) | Free tier | $0 |
| **Total** | | **~$15/month** |

### Monthly Running Costs (Production, Low Traffic)

| Service | Provider | Cost |
|---------|----------|------|
| Backend hosting | Railway Pro / Render | $20-40 |
| PostgreSQL | Managed | $15-25 |
| Redis | Managed | $10-15 |
| Pinecone | Standard | $70 |
| LLM API calls | Anthropic + OpenAI | $50-200 |
| Monitoring | Grafana Cloud Pro | $0-30 |
| Frontend | Vercel Pro | $0-20 |
| **Total** | | **~$165-400/month** |

### LLM API Costs (With Asahi Optimisation)

| Metric | Without Asahi | With Asahi |
|--------|---------------|------------|
| 1,000 requests/day | ~$15/day | ~$6/day |
| 10,000 requests/day | ~$150/day | ~$60/day |
| Monthly (10K/day) | ~$4,500 | ~$1,800 |
| **Savings** | | **~60%** |

The infrastructure cost ($15-400/month) is trivial compared to the LLM savings
($2,700+/month at 10K requests/day).
