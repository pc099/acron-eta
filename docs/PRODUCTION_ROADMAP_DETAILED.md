# ASAHI Production Roadmap — Detailed Plan

> **Purpose:** Single source of truth for taking ASAHI from current state to production and first customers.  
> **Sources:** TensorZero integration analysis, Frontend/Backend integration, Production GTM plan.  
> **Audience:** Engineering, product, and GTM; suitable for LLM/team handoff.

---

## Part 1: Document Summaries

### 1.1 ASAHI–TensorZero Backend Integration Analysis

**Summary:** Compares ASAHI (Python) and TensorZero (Rust) and recommends a **hybrid** approach.

**ASAHI today:**
- Python/FastAPI, 3-tier cache (exact, semantic, intermediate), AdvancedRouter (AUTOPILOT/GUIDED/EXPLICIT).
- **Strengths:** 85–92% cost savings, semantic cache, task-aware routing, dual-threshold logic.
- **Gaps:** ~20–50 ms latency, ~100 req/s, in-memory only, basic provider interface, no OpenAI SDK compatibility.

**TensorZero:**
- Rust gateway (Axum/Tokio), &lt;1 ms p99, 10k+ QPS, Redis + ClickHouse, 15+ providers, OpenAI client patching, React UI, TOML config.
- **Gaps:** No cost optimization, no semantic cache, no intelligent routing.

**Recommendation:** Keep ASAHI’s cost and caching logic; use TensorZero (or equivalent) for gateway, providers, persistence, and UX.

**Integration priorities:**
- **CRITICAL:** Rust gateway + ASAHI Python bridge, OpenAI compatibility, multi-provider + cost metadata, Redis + ASAHI semantic cache.
- **HIGH:** Cost dashboard, ClickHouse-style analytics, auth/multi-tenancy, production deploy.
- **KEEP IN ASAHI:** AdvancedRouter, semantic cache algorithms, task detection, optimizer logic.

**Timeline (from doc):** 4 weeks (Week 1 gateway, Week 2 cache/providers, Week 3 dashboard, Week 4 production).

---

### 1.2 ASAHI Frontend–Backend Integration

**Summary:** React frontend aligned with current and future backend APIs.

**Current backend (actual):**
- **Endpoints:** `POST /infer`, `GET /metrics`, `GET /health`, `GET /models`, analytics (Phase 6).
- **InferRequest:** prompt, task_id, latency_budget_ms, quality_threshold, cost_budget, user_id, routing_mode, quality_preference, latency_preference, model_override, document_id.
- **InferResponse (actual):** request_id, response, model_used, tokens_input, tokens_output, cost, latency_ms, cache_hit, routing_reason.  
  *(No cost_original, cost_optimized, cost_savings_percent, cache_tier, optimization_techniques in current API.)*

**Frontend doc assumptions (to implement or align):**
- Richer inference result: cost_original, cost_optimized, cost_savings_percent, cache_tier (tier1/tier2/tier3), optimization_techniques, quality_score, timestamp.
- Metrics: total_cost_savings, average_cost_savings_percent, cache_hit_rate_tier1/tier2/tier3, routing_mode_distribution, recent_inferences.
- Pages: Dashboard, Inference testing, Cache analytics, Routing, Providers, Cost analytics, Settings.
- Real-time: WebSocket for live inference/cost updates.

**Gap:** Backend does not yet expose cost_original/cost_optimized, per-tier cache rates, or recent_inferences in the shape the frontend doc assumes. Either extend backend responses or adapt frontend to current `/metrics` and `/infer` shapes.

---

### 1.3 Backend Analysis Download

**Summary:** Same content as **ASAHI–TensorZero Backend Integration Analysis** (duplicate). No additional actions.

---

### 1.4 ASAHI Production GTM Plan

**Summary:** 8–12 week path to production and first paying customers.

**Current state (from doc):**
- Phase 1 & 2 complete; 58% baseline savings; 16.67% cache hit rate (early); 52% savings per hit.
- Solid Python API, global exception handling, 95%+ test coverage.

**Production gaps:**
- No OpenAI SDK compatibility, no real-time cost dashboard, no enterprise auth/RBAC, in-memory only, no production observability.
- No pricing/onboarding, no support docs, no marketing site.

**Phases:**
- **Phase A (Week 1–2):** OpenAI compatibility, async perf (&lt;5 ms overhead), cost dashboard, auth, Redis/Postgres.
- **Phase B (Week 3–4):** Token optimization, cost predictor, monitoring, quality assurance.
- **Phase C (Week 5–6):** Pricing engine, onboarding, docs, marketing site.
- **Phase D (Week 7–12):** Pilots, direct sales, PLG, partnerships.

**Revenue targets:** Month 1 pilots; Month 3 ₹10L+ MRR; Month 6 ₹50L+ MRR.  
**Pricing:** Startup ₹15K/mo, Business ₹50K/mo, Enterprise ₹2L/mo.  
**Team:** 8–10 (engineering, sales, CS, marketing, ops).  
**Infra:** AWS, PostgreSQL, Redis, Pinecone; ~₹95K–1.9L/month.

---

## Part 2: Unified Production Roadmap

### 2.1 Strategic Choices

| Decision | Option A (Python-first) | Option B (TensorZero hybrid) |
|----------|-------------------------|------------------------------|
| **Gateway** | Keep FastAPI, optimize (async, pooling) | Rust gateway, ASAHI as Python “cost engine” behind it |
| **Latency target** | &lt;5 ms overhead (achievable in Python) | &lt;1 ms (Rust) |
| **Throughput target** | 500–1000 req/s | 1000+ req/s |
| **Timeline** | 6–8 weeks to production | 8–12 weeks (gateway + bridge) |
| **Risk** | Lower, single stack | Higher, two stacks + bridge |

**Recommendation for “take to production”:**  
- **Short term (first paying customers):** Option A — Python-first production (OpenAI compat, dashboard, Redis/Postgres, auth).  
- **Medium term (scale & enterprise):** Option B — Introduce Rust gateway and TensorZero-style infra when throughput and latency justify it.

The rest of this roadmap is written so it works for **Option A**; a final section adds **Option B (TensorZero hybrid)** as a follow-on phase.

---

### 2.2 Phase 0: Pre–Production (Current → Week 0)

**Goal:** Align codebase and docs with what production and GTM assume.

**Tasks:**

1. **Backend–frontend contract**
   - [ ] Decide canonical inference response: either extend `InferResponse` with `cost_original`, `cost_optimized`, `cost_savings_percent`, `cache_tier`, `optimization_techniques`, `quality_score` (and optionally timestamp), or document “current minimal response” and have frontend derive savings from `/metrics` and single-request `cost`.
   - [ ] Document openapi/schemas and publish (e.g. `docs/api_openapi.yaml` or link from README).

2. **Metrics API**
   - [ ] Ensure `GET /metrics` returns: total_cost, cache_hit_rate, cache_size, cache_cost_saved, requests, uptime_seconds (already there); add if needed: per-tier hit counts or rates for dashboard (e.g. tier1_hits, tier2_hits, tier3_hits or equivalent).
   - [ ] Optional: add `GET /analytics/recent-inferences` (or include last N in `/metrics`) for “recent inferences” table with request_id, model_used, cost, cache_hit, routing_reason, timestamp.

3. **Integration roadmap vs code**
   - [ ] Mark in `docs/INTEGRATION_ROADMAP.md` which steps are done (e.g. Step 1 exception handler, Step 2 Phase 2 pipeline).
   - [ ] In `docs/HANDOFF_DOCUMENT.md`, add one line referencing this production roadmap and the chosen path (A vs B).

**Output:** Clear API contract and roadmap state so frontend and next phases don’t assume non-existent fields.

---

### 2.3 Phase 1: Production Polish (Week 1–2)

**Goal:** Customer-facing reliability, compatibility, and visibility.

#### 1.1 OpenAI SDK compatibility (Week 1, Day 1–2)

- [ ] **Implement OpenAI-compatible endpoint**  
  - Either: `POST /openai/v1/chat/completions` (or `/v1/chat/completions`) that accepts OpenAI request body and returns OpenAI response shape.  
  - Or: document proxy setup (e.g. nginx/routing) so that “OpenAI base URL” points to ASAHI and path is `/v1/chat/completions`.
- [ ] **Request translation:** Map `messages`, `model`, `max_tokens`, etc. to ASAHI `InferRequest` (prompt, quality_threshold, routing_mode, model_override if model is specified).
- [ ] **Response translation:** Map ASAHI `InferenceResult` to OpenAI `choices[].message.content`, `usage` (prompt_tokens, completion_tokens), and optionally `model`.
- [ ] **Errors:** Return OpenAI-style error body and status codes where applicable.
- [ ] **Optional:** Python SDK helper that patches `openai.OpenAI` base URL (or a thin client) so existing code works with minimal change. Document in `docs/LOCAL_TESTING_GUIDE.md` and production docs.

**Acceptance:** Existing OpenAI code (with base URL override) runs against ASAHI without code change; cost optimization is applied.

#### 1.2 Performance (Week 1, Day 3–4)

- [ ] **Async where it matters:** Ensure cache and provider calls in the hot path are non-blocking (async or run_in_executor) so that a single process can handle many concurrent requests.
- [ ] **Connection pooling:** Reuse HTTP client(s) for LLM and embedding APIs; use a single Cohere/OpenAI client per process where applicable.
- [ ] **Cache lookup:** Keep Tier 1 in-process; for Tier 2, ensure embedding + vector lookup don’t block event loop (async or thread pool).
- [ ] **Target:** &lt;5 ms added latency (p95) for cache miss path over “direct LLM call”; 500+ req/s per instance under load test.

**Acceptance:** Load test (e.g. `wrk` or `locust`) shows p95 &lt;100 ms end-to-end and no regression in cost or cache behavior.

#### 1.3 Cost dashboard backend (Week 1, Day 5–7)

- [ ] **Metrics endpoint:** Already have `GET /metrics` and Phase 6 analytics. Expose:
  - For dashboard: cache hit rate (overall and per-tier if available), total cost, total requests, cost saved (if computed).
- [ ] **Optional:** `GET /analytics/cost-summary?period=24h` returning: total_cost, total_requests, cache_hit_rate, cost_saved, by_model or by_task breakdown (reuse existing analytics where possible).
- [ ] **Optional:** WebSocket or SSE for “latest inference” events (e.g. `GET /ws/events` or SSE) so dashboard can show live updates. If not in scope, document “poll /metrics every N seconds” for MVP.

**Acceptance:** Frontend (or curl) can get all numbers needed for “cost savings” and “cache performance” widgets.

#### 1.4 Auth and multi-tenancy (Week 2, Day 8–10)

- [ ] **API key auth:** Validate API key on every request (except `/health`, `/docs`, `/openapi.json`). Store keys in config or DB (e.g. PostgreSQL); support key scopes if needed (e.g. `infer`, `analytics`).
- [ ] **Request context:** Attach `org_id` and `user_id` to request state from key; use in optimizer for cache namespacing and future billing.
- [ ] **RBAC (minimal):** Optional: restrict `/governance/*` and analytics to “admin” keys; infer to “infer” or “all”.
- [ ] **Audit:** Log auth failures and sensitive actions (e.g. policy change, key creation) via existing `AuditLogger`.

**Acceptance:** Requests without valid key get 401; with key, org_id is available for cache key prefix and logging.

#### 1.5 Persistence and production runtime (Week 2, Day 11–14)

- [ ] **Redis for Tier 1:** Replace in-memory Tier 1 cache with Redis (key: e.g. `asahi:t1:{hash(prompt)}`, value: JSON of response, model, cost; TTL from config). Fallback to in-memory if Redis unavailable (or fail fast in production).
- [ ] **PostgreSQL:** Use for: API keys, orgs, policies, audit log (if not file-based). Add minimal schema (orgs, api_keys, policies) and run migrations (e.g. Alembic).
- [ ] **Pinecone (or external vector DB):** For Tier 2, keep current in-memory vector DB for single-node; document env vars and index name for Pinecone so production can switch.
- [ ] **Config:** All connection strings and feature flags from env (e.g. `REDIS_URL`, `DATABASE_URL`, `PINECONE_*`). No hardcoded URLs.
- [ ] **Docker:** Dockerfile for API server; docker-compose with api + redis + postgres (and optional Pinecone client). Health checks for API and dependencies.
- [ ] **Secrets:** API keys and DB credentials from env or secret manager; never in repo.

**Acceptance:** With Redis and Postgres up, API starts; Tier 1 survives restarts; keys and orgs are stored in DB.

---

### 2.4 Phase 2: Enterprise and Observability (Week 3–4)

**Goal:** Scale, observability, and quality assurance.

#### 2.1 Token optimization in pipeline (Week 3)

- [ ] **Wire TokenOptimizer** in `InferenceOptimizer.infer()` (see `docs/INTEGRATION_ROADMAP.md` Step 3): before routing, call token optimizer; use optimized prompt for inference; respect quality_risk (e.g. skip or warn when high).
- [ ] **Metrics:** Expose token savings (e.g. original_tokens vs optimized_tokens) in response or metrics.

**Acceptance:** Configurable; when enabled, token usage drops for long prompts without degrading quality (validated by tests and spot checks).

#### 2.2 Feature store in pipeline (Week 3)

- [ ] **Wire FeatureEnricher** in `InferenceOptimizer.infer()` when `user_id` or `organization_id` is present (see INTEGRATION_ROADMAP Step 4). Enrich prompt; on timeout/error, fall back to original prompt.
- [ ] **Optional:** FeatureMonitor for enrichment success/failure and impact.

**Acceptance:** With feature store configured and user/org id provided, prompts are enriched; no hard dependency (graceful fallback).

#### 2.3 Cost forecasting and recommendations (Week 3–4)

- [ ] **Use existing Phase 6:** ForecastingModel, AnomalyDetector, RecommendationEngine already exist. Expose via existing `/analytics/forecast`, `/analytics/anomalies`, `/analytics/recommendations`.
- [ ] **Dashboard:** Frontend consumes these for “cost forecast”, “alerts”, “recommendations” panels.

**Acceptance:** Forecast and recommendations are available via API and visible in UI.

#### 2.4 Observability (Week 4)

- [ ] **Prometheus:** Already have `/analytics/prometheus`. Ensure it’s scraped (or document scrape config). Add key metrics: request count, latency histogram, cache hit rate, cost total.
- [ ] **Structured logs:** Request_id, org_id, model, cost, cache_hit in JSON logs. No PII in logs.
- [ ] **Alerts (optional):** Define alerts for error rate, latency p99, cache hit rate drop (e.g. in Prometheus/Grafana or provider).

**Acceptance:** One dashboard shows QPS, latency, errors, cache hit rate, and cost.

#### 2.5 Quality assurance (Week 4)

- [ ] **QualityMonitor (optional):** If baseline vs optimized comparison is required, add a path that runs both and compares (e.g. in staging or sampling). Otherwise, rely on existing quality_threshold and routing logic.
- [ ] **Regression tests:** Automated tests for critical paths (infer with cache hit/miss, routing modes, auth, Redis/DB down).

**Acceptance:** Quality regression tests exist; no known regressions in cost or quality.

---

### 2.5 Phase 3: GTM and Packaging (Week 5–6)

**Goal:** Pricing, onboarding, and sales enablement.

#### 3.1 Pricing and billing (Week 5)

- [ ] **Plans in config or DB:** e.g. Startup (100K requests/mo), Business (1M/mo), Enterprise (unlimited). Store per-org plan and limits.
- [ ] **Usage tracking:** Count requests and cost per org (from existing tracker or new table). Aggregate by day/month.
- [ ] **Billing API (internal or admin):** Return usage and computed bill for an org (formula: base + overage). No payment processing required for MVP; can be manual invoicing.
- [ ] **Enforcement (optional):** Soft limit (alert) or hard limit (reject with 429) when org exceeds plan.

**Acceptance:** Per-org usage and bill amount are computable and exposed to admin/CS.

#### 3.2 Onboarding (Week 5–6)

- [ ] **Self-serve signup:** Form or landing page → create org, create API key, send email with key and docs link.
- [ ] **Stored in DB:** Org id, name, plan, created_at; API key hashed or stored with prefix for validation.
- [ ] **Welcome email:** Link to docs, quick start (e.g. curl or Python snippet with base URL and key).

**Acceptance:** New “customer” can sign up, get key, and call API within minutes.

#### 3.3 Documentation and marketing (Week 6)

- [ ] **API docs:** OpenAPI served from app; use for “reference”. Add “Quick start”, “OpenAI compatibility”, “Routing modes”, “Authentication” in `docs/` or docs site.
- [ ] **Integration guide:** Step-by-step: get key, set base URL, run first request. Include Python and curl examples.
- [ ] **ROI / pricing page:** Simple calculator or table: “Current monthly spend” → “Estimated savings with ASAHI” (e.g. 85%).
- [ ] **Landing page (optional):** Hero, proof points (e.g. 85–92% savings), CTA to sign up or contact.

**Acceptance:** Sales or support can send links to docs and pricing; developers can integrate without back-and-forth.

---

### 2.6 Phase 4: First Customers (Week 7–12)

**Goal:** Pilots and first paying customers.

#### 4.1 Pilots (Week 7–8)

- [ ] **Pilot criteria:** AI-first usage, willingness to share feedback and usage patterns.
- [ ] **Process:** Qualify → onboard (key, docs) → 14-day trial with support → collect savings data and NPS/feedback.
- [ ] **Success:** 3+ pilots with measured savings and positive feedback.

#### 4.2 Sales and PLG (Week 7–12)

- [ ] **Direct outbound:** Use GTM plan templates (email, LinkedIn) and demo flow (qualification → demo → trial → close).
- [ ] **Self-serve:** Signup → trial → in-app or email “savings so far” → upgrade to paid when limits hit or trial ends.
- [ ] **Partnerships (optional):** Referral or rev-share with cloud/consulting partners.

#### 4.3 Customer success

- [ ] **Onboarding:** Day 0 welcome; Day 1–2 check-in if no usage; Day 7 “savings report” email or in-app.
- [ ] **Support:** Email or in-app; document SLAs (e.g. response &lt;24 h for non-critical).
- [ ] **Retention:** Monitor usage and savings; proactive outreach if usage drops or errors spike.

**Acceptance:** Repeatable process to acquire and retain first 10–20 customers.

---

### 2.7 Phase 5 (Optional): TensorZero-Style Hybrid

**Goal:** If/when you need &lt;5 ms gateway latency and 1000+ QPS at the edge.

**Trigger:** Demand for higher throughput or lower latency than Python-first can deliver; or strategic decision to adopt TensorZero stack.

**Tasks (high level):**

1. **Rust gateway:** Stand up Axum (or equivalent) gateway; forward inference to ASAHI Python service (e.g. `POST http://asahi-engine/optimize` or `POST .../infer`). Translate OpenAI-shaped requests from gateway to ASAHI and back.
2. **ASAHI as cost engine:** Keep current Python app as “optimization service”: receives prompt + constraints, returns optimized request (model, prompt) or full response; gateway or a separate layer calls LLM provider.
3. **Cache:** Tier 1 in Redis (gateway or Python); Tier 2/3 in Python (or reimplement Tier 2 in Rust using same similarity/threshold logic). Document cache key format so both sides stay in sync.
4. **Providers:** Either keep calling from Python, or move provider calls to Rust and pass cost metadata from ASAHI (e.g. model choice, cost estimate) from Python to Rust.
5. **Dashboard and auth:** Use TensorZero UI or current React app; auth at gateway; org_id passed to ASAHI for namespacing.

**Timeline:** 4–8 weeks after Phase 1–4, depending on TensorZero codebase access and integration depth.

---

## Part 3: Task Checklist (What to Build and When)

### Must-have before “production” (first paying customer)

| # | Task | Phase | Owner / Notes |
|---|------|--------|----------------|
| 1 | OpenAI-compatible endpoint or proxy + docs | 1.1 | Backend |
| 2 | Async + connection pooling; &lt;5 ms overhead target | 1.2 | Backend |
| 3 | Dashboard backend: metrics + optional cost-summary/SSE | 1.3 | Backend |
| 4 | API key auth + org_id in request state | 1.4 | Backend |
| 5 | Redis Tier 1 cache | 1.5 | Backend |
| 6 | PostgreSQL for orgs, keys, policies | 1.5 | Backend |
| 7 | Docker + docker-compose (api, redis, postgres) | 1.5 | DevOps |
| 8 | Wire TokenOptimizer in optimizer | 2.1 | Backend |
| 9 | Wire FeatureEnricher (optional but recommended) | 2.2 | Backend |
| 10 | Prometheus + logging + optional alerts | 2.4 | DevOps |
| 11 | Pricing/plans and usage tracking per org | 3.1 | Backend |
| 12 | Signup + API key creation + welcome email | 3.2 | Full-stack |
| 13 | Public API docs + integration guide | 3.3 | Docs |
| 14 | Cost dashboard UI (metrics + cache + savings) | 1.3 + 2.3 | Frontend |
| 15 | Inference testing UI (prompt + routing_mode + result) | 3.3 | Frontend |

### Should-have for “enterprise” and scale

| # | Task | Phase | Owner / Notes |
|---|------|--------|----------------|
| 16 | Pinecone (or external vector DB) for Tier 2 in production | 1.5 / 2 | Backend |
| 17 | Batching in pipeline (INTEGRATION_ROADMAP Step 5) | 2 | Backend |
| 18 | RBAC and policy checks in optimizer | 1.4 / 2 | Backend |
| 19 | WebSocket or SSE for live dashboard updates | 1.3 | Backend + Frontend |
| 20 | Quality regression / A-B testing (optional) | 2.5 | Backend |
| 21 | Billing automation (invoicing or stripe) | 3.1 | Backend + Ops |
| 22 | Landing page + ROI calculator | 3.3 | Marketing / Frontend |

### Later (TensorZero hybrid or scale)

| # | Task | Phase | Owner / Notes |
|---|------|--------|----------------|
| 23 | Rust gateway + ASAHI Python bridge | 5 | Backend |
| 24 | Multi-provider layer (15+ providers) | 5 | Backend |
| 25 | ClickHouse or similar for analytics | 5 | Data / DevOps |

---

## Part 4: API and Data Alignment

### 4.1 Current vs assumed response shape

**Current `InferResponse` (actual):**
- request_id, response, model_used, tokens_input, tokens_output, cost, latency_ms, cache_hit, routing_reason.

**Frontend/doc “ideal” for dashboard:**
- cost_original, cost_optimized, cost_savings, cost_savings_percent, cache_tier (tier1|tier2|tier3), optimization_techniques[], quality_score, timestamp.

**Recommendation:**
- **Option A (minimal):** Keep current response. Dashboard computes “savings” by comparing `cost` to a baseline (e.g. same request to a fixed expensive model) or from aggregate `/metrics` (total_cost, cache_cost_saved). No backend change.
- **Option B (rich):** Add to backend: for each request, store or compute baseline cost (e.g. “cost if we had used gpt-4 for this request”); return in response: cost_original, cost_optimized (= cost), cost_savings_percent, cache_tier (infer from routing_reason or add field). Add optimization_techniques and quality_score if available.

Choose one and document in OpenAPI and HANDOFF_DOCUMENT.

### 4.2 Metrics and analytics

- **Already available:** GET /metrics (requests, total_cost, cache_hit_rate, cache_size, cache_cost_saved, uptime_seconds). Phase 6: cost-breakdown, trends, forecast, anomalies, recommendations, cache-performance, latency-percentiles, prometheus.
- **Optional additions:** Per-tier hit counts (tier1_hits, tier2_hits, tier3_hits) in `/metrics` or `/analytics/cache-performance`; `recent_inferences` (last N) for dashboard table.

---

## Part 5: Timeline Overview

```
Week 0     Phase 0:   API contract, metrics alignment, docs update
Week 1–2   Phase 1:   OpenAI compat, perf, dashboard backend, auth, Redis/Postgres, Docker
Week 3–4   Phase 2:   Token + feature-store wiring, forecasting/recommendations, observability, QA
Week 5–6   Phase 3:   Pricing, onboarding, docs, marketing/landing
Week 7–8   Phase 4:   Pilots, sales process, first paying customers
Week 9–12  Phase 4:   Scale to 10–20 customers, refine onboarding and support
Optional   Phase 5:   TensorZero hybrid (Rust gateway + ASAHI engine)
```

**Critical path:** Phase 0 → 1.1 (OpenAI) → 1.4 (Auth) → 1.5 (Redis/Postgres) → 3.2 (Onboarding) → 4.1 (Pilots).

---

## Part 6: Success Criteria

**Technical**
- OpenAI-compatible flow works with existing customer code (base URL + key).
- p95 latency overhead &lt;5 ms; single instance 500+ req/s.
- Tier 1 in Redis; Tier 2 semantic cache working; cost savings 85%+ in tests.
- Uptime 99.9% (measured over 30 days).
- No PII in logs; API keys and secrets from env.

**Product**
- Dashboard shows cost savings, cache hit rate, and recent activity.
- At least one “cost summary” or “savings” API consumed by dashboard.
- Docs allow a new developer to integrate in &lt;30 minutes.

**Business**
- 3+ pilots with measured savings and feedback.
- Pricing and usage tracking in place for first paid conversions.
- First paying customer within 12 weeks of starting Phase 1.

---

## Part 7: Accounts and Integrations for Deployment

Create these accounts **before or during** the deployment phases. All have free or low-cost tiers suitable for dev/staging and production.

### 7.1 Required (core inference and Phase 1)

| Integration | Purpose | Env var(s) | Sign-up / Where | What to create |
|-------------|---------|------------|------------------|----------------|
| **OpenAI** | GPT models (routing, inference) | `OPENAI_API_KEY` | platform.openai.com | API key in API Keys |
| **Anthropic** | Claude models (inference) | `ANTHROPIC_API_KEY` | console.anthropic.com | API key |
| **Cohere** | Embeddings for Tier 2 semantic cache | `COHERE_API_KEY` | dashboard.cohere.com | API key (free tier: 1K calls/mo) |
| **GitHub** | Repo, CI/CD (Actions) | — | github.com | Repo; add secrets for deploy |
| **Cloud host** (one of below) | Run API + optional managed DBs | Provider-specific | See 7.2 | Project; get `DATABASE_URL`, `REDIS_URL` if using managed |

**Governance (required for production):**
| Integration | Purpose | Env var(s) | Notes |
|-------------|---------|------------|--------|
| **Encryption key** | Data-at-rest (policies, audit) | `ASAHI_ENCRYPTION_KEY` | Generate: `python -c "import secrets; print(secrets.token_hex(32))"` — no account |

### 7.2 Cloud provider (pick one for hosting)

| Provider | What you get | Typical monthly cost | Sign-up | Accounts to create |
|----------|--------------|------------------------|---------|---------------------|
| **Railway** | Containers + Postgres + Redis add-ons | $5–20 | railway.app | Project; add Postgres + Redis from dashboard; copy `DATABASE_URL`, `REDIS_URL` |
| **Render** | Web service + managed Postgres/Redis | $7–25 | render.com | Web Service + PostgreSQL (+ Redis optional); get URLs from dashboard |
| **Fly.io** | Edge containers | $5–15 | fly.io | App; attach Postgres/Upstash Redis or external |
| **DigitalOcean** | Droplet + Managed DBs | $12–30 | digitalocean.com | Droplet; Managed Redis; Managed PostgreSQL (or App Platform) |
| **AWS** (e.g. Lightsail / ECS) | Containers + RDS + ElastiCache | $15–40+ | aws.amazon.com | VPC; RDS (Postgres); ElastiCache (Redis); ECS/Lightsail for API |

**Recommendation for first deployment:** Railway or Render — deploy from GitHub, add Postgres and Redis in the same place, minimal ops.

### 7.3 Persistence (Phase 1.5 — production cache and DB)

| Integration | Purpose | Env var(s) | When to create account |
|-------------|---------|------------|------------------------|
| **PostgreSQL** | Orgs, API keys, policies, audit | `DATABASE_URL` | Phase 1.5. Often from cloud host (Railway/Render/DO/RDS). |
| **Redis** | Tier 1 exact-match cache, rate limit, sessions | `REDIS_URL` | Phase 1.5. Often from cloud host; or Upstash (serverless). |
| **Pinecone** | Tier 2 vector store (semantic cache) | `PINECONE_API_KEY`, `PINECONE_ENVIRONMENT` | Phase 1.5 or when scaling Tier 2. Create index: name e.g. `asahi-vectors`, dimension=1024, metric=cosine. |

**Optional Redis alternative:** Upstash (upstash.com) — serverless Redis; use when not using Railway/Render Redis.

### 7.4 Optional (Phase 2–3 and later)

| Integration | Purpose | Env var(s) | When needed |
|-------------|---------|------------|-------------|
| **Tecton** | Feature store (prompt enrichment) | `TECTON_API_KEY` | Step 4 / Phase 2 if using remote feature store |
| **Kafka** | Event streaming (events) | `KAFKA_BOOTSTRAP_SERVERS`, `ENABLE_KAFKA` | Only if enabling Kafka in config |
| **Docker Hub** | Container registry for CI/CD | `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | When building/pushing images in GitHub Actions |
| **Sentry** | Error tracking | `SENTRY_DSN` | Observability (Phase 2) |
| **Grafana Cloud** | Prometheus + dashboards | Grafana scrape config | Observability (Phase 2) |
| **Vercel** | Frontend (React dashboard) | — | When deploying dashboard (Phase 3/J) |
| **Stripe** | Billing/payments | `STRIPE_SECRET_KEY`, etc. | Phase 3 if automating billing |
| **Email (SendGrid/SES/etc.)** | Welcome and transactional email | e.g. `SENDGRID_API_KEY` | Phase 3 onboarding (welcome email) |

### 7.5 GitHub repository secrets (for CI/CD and deploy)

Add under **Settings → Secrets and variables → Actions** (and, if applicable, to your cloud provider’s env/config):

```
# LLM and embeddings
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
COHERE_API_KEY=...

# Persistence (from cloud provider or managed services)
DATABASE_URL=postgresql://user:pass@host:5432/dbname
REDIS_URL=redis://:pass@host:6379/0

# Pinecone (when using production Tier 2)
PINECONE_API_KEY=...
PINECONE_ENVIRONMENT=us-east-1

# Governance
ASAHI_ENCRYPTION_KEY=<64-char-hex-from-secrets.token_hex(32)>

# Registry (if using Docker Hub in CI)
DOCKERHUB_USERNAME=...
DOCKERHUB_TOKEN=...

# Cloud deploy (pick one)
RAILWAY_TOKEN=...        # Railway
RENDER_API_KEY=...       # Render
FLY_API_TOKEN=...       # Fly.io
```

### 7.6 Checklist: accounts to create before deployment

- [ ] **GitHub** — repo exists; secrets added for chosen cloud + API keys
- [ ] **OpenAI** — account + API key
- [ ] **Anthropic** — account + API key
- [ ] **Cohere** — account + API key (needed for Phase 2 Tier 2 semantic cache)
- [ ] **Cloud provider** — account; create project and (if using managed) Postgres + Redis; note `DATABASE_URL`, `REDIS_URL`
- [ ] **Pinecone** — account; create index `asahi-vectors` (dimension 1024, cosine) when moving Tier 2 to production
- [ ] **ASAHI_ENCRYPTION_KEY** — generated and stored in env/secrets (no account)
- [ ] **Docker Hub** — account + token if CI builds and pushes images
- [ ] (Optional) **Upstash** — if using serverless Redis instead of provider Redis
- [ ] (Later) **Sentry / Grafana / Vercel / Stripe / Email** — as you implement observability, frontend, billing, and onboarding

---

## Part 8: References

- **Integration (current codebase):** `docs/INTEGRATION_ROADMAP.md`, `docs/HANDOFF_DOCUMENT.md`
- **Local testing:** `docs/LOCAL_TESTING_GUIDE.md`
- **TensorZero hybrid (detailed):** `asahi_docs/ASAHI_TensorZero_Backend_Integration_Analysis.md`
- **Frontend/backend contract:** `asahi_docs/ASAHI_Frontend_Backend_Integration.md`
- **GTM and revenue:** `asahi_docs/ASAHI_Production_GTM_Plan.md`
- **Accounts and deploy steps:** `docs/PRODUCTION_ROADMAP.md` (Section 1: Accounts and Services to Set Up; Steps E–H)

---

**Document version:** 1.1  
**Last updated:** 2026-02-13  
**Next review:** After Phase 0 and Week 1 completion
