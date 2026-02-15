# Asahi API Contract

This document summarizes the canonical API for the Asahi inference cost optimizer. The full OpenAPI 3 schema is available at **`/openapi.json`** when the server is running (e.g. `http://localhost:8000/openapi.json`). Interactive docs: **`/docs`** (Swagger UI), **`/redoc`** (ReDoc).

---

## Inference

### `POST /infer`

**Request body (`InferRequest`):**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `prompt` | string | Yes | User query (1–100000 chars) |
| `task_id` | string | No | Task identifier for tracking |
| `latency_budget_ms` | int | No | Max latency (default 300) |
| `quality_threshold` | float | No | Min quality 0–5 (default 3.5) |
| `cost_budget` | float | No | Max dollar cost |
| `user_id` | string | No | Caller identity |
| `organization_id` | string | No | Org for cache/feature enrichment |
| `routing_mode` | string | No | `autopilot` \| `guided` \| `explicit` |
| `quality_preference` | string | No | For guided: low/medium/high/max |
| `latency_preference` | string | No | For guided |
| `model_override` | string | No | For explicit mode |
| `document_id` | string | No | For Tier 3 workflow |

**Response (`InferResponse`):**

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | string | Request trace ID |
| `response` | string | LLM response text |
| `model_used` | string | Selected model |
| `tokens_input`, `tokens_output` | int | Token counts |
| `cost` | float | Dollar cost |
| `latency_ms` | float | End-to-end latency |
| `cache_hit` | bool | Whether from cache |
| `cache_tier` | int | 0=miss, 1/2/3=tier |
| `routing_reason` | string | Why this model |
| `cost_original` | float? | Baseline cost (dashboard) |
| `cost_savings_percent` | float? | Savings vs baseline |
| `optimization_techniques` | string[]? | e.g. cache_tier_1, semantic_cache |

---

## OpenAI compatibility

### `POST /v1/chat/completions`

Accepts OpenAI-style `messages`, `model`, `max_tokens`, etc. Returns `choices[].message.content`, `usage`. Use Asahi as base URL to drop-in optimize existing OpenAI code.

---

## Metrics and analytics

| Endpoint | Description |
|----------|-------------|
| `GET /metrics` | total_cost, cache_hit_rate, cache_size, cache_cost_saved, requests, uptime_seconds, tier1_hits, tier2_hits, tier3_hits |
| `GET /analytics/cost-summary?period=24h` | Dashboard: total_cost, total_requests, cache_hit_rate, cache_cost_saved, uptime_seconds |
| `GET /analytics/recent-inferences?limit=50` | Last N inference events (request_id, model_used, cost, cache_hit, timestamp, etc.) |
| `GET /analytics/cost-breakdown` | By model/task/period |
| `GET /analytics/forecast` | Cost forecast |
| `GET /analytics/anomalies` | Anomaly detection |
| `GET /analytics/recommendations` | Optimization recommendations |
| `GET /analytics/prometheus` | Prometheus text exposition |

Analytics and governance endpoints require scope `analytics` or `admin` or `all` when API key has scopes.

---

## Auth and governance

- **API key:** `Authorization: Bearer <key>`. When `auth_api_key_required` is true, unauthenticated requests get 401.
- **Scopes:** Keys may have `infer`, `analytics`, `admin`, `all` (or `*` for full access). `/infer` requires infer/all; analytics require analytics/admin/all; `/governance/*` requires admin/all.
- **Signup:** `POST /signup` (self-serve: body `org_name`, `user_id`, optional `email`; creates org and API key when `DATABASE_URL` is set; optional welcome email when `SENDGRID_API_KEY` is set). Returns `org_id`, `api_key`, `org_name`; key is shown only once.
- **Governance:** `POST /governance/api-keys` (create key; requires X-Admin-Secret or admin scope), `GET/POST /governance/policies/{org_id}`, `GET /governance/usage?org_id=&period=day|month` (request count and cost; admin only), `GET /governance/audit`, `GET /governance/compliance/report`.

---

## Health and models

| Endpoint | Description |
|----------|-------------|
| `GET /health` | status, version, uptime, components |
| `GET /models` | Registered models with pricing and quality |

---

## OpenAPI schema

- **Runtime:** `GET /openapi.json` (when server is running).
- **Export:** To save the schema to a file: `curl http://localhost:8000/openapi.json > docs/openapi.json` (optional; not committed by default so it stays in sync with code).
