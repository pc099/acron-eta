# API and Configuration Specification

> Comprehensive API reference and configuration guide for all phases.  
> This is the contract that all client integrations and internal components rely on.

---

## 1. API Design Principles

- **REST/JSON** for all public endpoints (Phase 1-7).
- **Versioned** via URL prefix: `/api/v1/`, `/api/v2/`.
- **Idempotent** GETs; non-idempotent POSTs include `request_id` for deduplication.
- **Structured errors** with `error`, `message`, `details` fields on all non-2xx responses.
- **Content-Type**: `application/json` for all request/response bodies.
- **Authentication**: via `Authorization: Bearer <api_key>` header (Phase 7+).
- **Rate limiting**: 429 response with `Retry-After` header.
- **CORS**: configurable allowed origins.

---

## 2. Core Endpoints (Phase 1)

### 2.1 POST /api/v1/infer

Main inference endpoint.

**Request:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `prompt` | string | yes | -- | User query (1-100,000 chars) |
| `task_id` | string | no | null | Optional task identifier for tracking |
| `latency_budget_ms` | int | no | 300 | Max acceptable latency |
| `quality_threshold` | float | no | 3.5 | Minimum quality score (0-5) |
| `cost_budget` | float | no | null | Max dollar cost per request |
| `user_id` | string | no | null | Caller identity for analytics |

**Response 200:**

```json
{
  "request_id": "req_a1b2c3d4",
  "response": "The document discusses...",
  "model_used": "claude-3-5-sonnet",
  "tokens_input": 2150,
  "tokens_output": 45,
  "cost": 0.003,
  "latency_ms": 245,
  "cache_hit": false,
  "routing_reason": "Best quality/cost ratio among 3 candidates"
}
```

**Response 400:**

```json
{
  "error": "validation_error",
  "message": "prompt is required and must be 1-100000 characters",
  "details": {"field": "prompt", "constraint": "min_length"}
}
```

**Response 429:**

```json
{
  "error": "rate_limited",
  "message": "Too many requests",
  "retry_after_seconds": 10
}
```

**Response 503:**

```json
{
  "error": "service_unavailable",
  "message": "All model providers are currently unavailable",
  "retry_after_seconds": 30
}
```

### 2.2 GET /api/v1/metrics

Aggregated analytics.

**Response 200:**

```json
{
  "total_cost": 12.45,
  "total_requests": 342,
  "avg_latency_ms": 145.2,
  "cache_hit_rate": 0.27,
  "cost_by_model": {
    "gpt-4-turbo": 6.23,
    "claude-opus-4": 4.10,
    "claude-3-5-sonnet": 2.12
  },
  "estimated_savings_vs_gpt4": 18.95
}
```

### 2.3 GET /api/v1/models

Available models and their profiles.

**Response 200:**

```json
{
  "models": [
    {
      "name": "claude-3-5-sonnet",
      "provider": "anthropic",
      "cost_per_1k_input": 0.003,
      "cost_per_1k_output": 0.015,
      "quality": 4.1,
      "latency_ms": 150,
      "availability": "available"
    }
  ],
  "task_types": ["summarization", "reasoning", "faq", "coding", "translation"],
  "default_constraints": {
    "summarization": {"quality": 3.5, "latency": 300},
    "reasoning": {"quality": 4.2, "latency": 500}
  }
}
```

### 2.4 GET /api/v1/health

System health check.

**Response 200:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-02-08T10:35:00Z",
  "uptime_seconds": 3600,
  "components": {
    "cache": "healthy",
    "router": "healthy",
    "tracker": "healthy",
    "api_clients": "healthy"
  }
}
```

---

## 3. Phase 2 Endpoint Extensions

### 3.1 POST /api/v2/infer

Extended inference with routing modes and tiered caching.

**Additional request fields:**

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `routing_mode` | string | no | `"autopilot"` | `autopilot`, `guided`, or `explicit` |
| `quality_preference` | string | no | null | `low`, `medium`, `high`, `max` (GUIDED mode) |
| `latency_preference` | string | no | null | `slow`, `normal`, `fast`, `instant` (GUIDED mode) |
| `model` | string | no | null | Model override (EXPLICIT mode) |

**Additional response fields:**

```json
{
  "...base fields...",
  "routing_mode": "guided",
  "cache": {
    "hit": true,
    "tier": 2,
    "similarity": 0.92,
    "cached_query": "How do I summarize documents?"
  },
  "alternatives": [
    {
      "model": "mistral-7b",
      "estimated_cost": 0.001,
      "estimated_quality": 3.8,
      "savings_percent": 67
    }
  ]
}
```

### 3.2 GET /api/v2/metrics

Extended metrics with per-tier cache stats.

**Additional response fields:**

```json
{
  "...base fields...",
  "cache_stats": {
    "tier_1": {"hits": 250, "misses": 750, "hit_rate": 0.25},
    "tier_2": {"hits": 180, "misses": 570, "hit_rate": 0.24},
    "tier_3": {"hits": 75, "misses": 495, "hit_rate": 0.13},
    "overall_hit_rate": 0.505
  },
  "mode_distribution": {
    "autopilot": 600,
    "guided": 300,
    "explicit": 100
  }
}
```

---

## 4. Phase 6 Analytics Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/analytics/cost-breakdown` | GET | Cost by model/task/period |
| `/api/v1/analytics/trends` | GET | Time-series trend data |
| `/api/v1/analytics/forecast` | GET | Cost predictions |
| `/api/v1/analytics/anomalies` | GET | Current anomalies |
| `/api/v1/analytics/recommendations` | GET | Optimisation suggestions |

Query parameters: `period` (hour/day/week/month), `group_by` (model/task_type/user).

---

## 5. Phase 7 Management Endpoints

| Endpoint | Method | Auth Required | Description |
|----------|--------|---------------|-------------|
| `/api/v1/org/policy` | GET/PUT | admin | Organization policy |
| `/api/v1/org/users` | GET/POST/DELETE | admin | User management |
| `/api/v1/org/roles` | GET/POST | admin | Role management |
| `/api/v1/org/audit-log` | GET | admin, billing | Audit trail |
| `/api/v1/org/compliance-report` | GET | admin | Compliance report |
| `/api/v1/auth/keys` | POST/DELETE | admin | API key management |

---

## 6. Phase 8 Agent Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/swarm/workflow` | POST | Execute agent workflow |
| `/api/v1/swarm/status/{workflow_id}` | GET | Workflow status |
| `/api/v1/swarm/metrics` | GET | Agent swarm metrics |
| `/api/v1/swarm/profiles` | GET/POST | Agent profiles |

---

## 7. HTTP Status Code Reference

| Code | Meaning | When |
|------|---------|------|
| 200 | Success | Normal response |
| 201 | Created | New resource created (API key, tenant) |
| 400 | Bad Request | Validation failure |
| 401 | Unauthorized | Missing or invalid API key |
| 403 | Forbidden | Insufficient permissions or policy violation |
| 404 | Not Found | Unknown endpoint or resource |
| 429 | Too Many Requests | Rate limit or budget exceeded |
| 500 | Internal Server Error | Unexpected error |
| 503 | Service Unavailable | All providers down |

---

## 8. Configuration Reference

### 8.1 Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | yes (if using Claude) | -- | Anthropic API key |
| `OPENAI_API_KEY` | yes (if using GPT) | -- | OpenAI API key |
| `COHERE_API_KEY` | yes (Phase 2) | -- | Cohere embedding API key |
| `PINECONE_API_KEY` | yes (Phase 2 prod) | -- | Pinecone vector DB key |
| `REDIS_URL` | no | `redis://localhost:6379` | Redis connection URL |
| `DATABASE_URL` | no | `sqlite:///asahi.db` | Primary database |
| `ASAHI_ENCRYPTION_KEY` | yes (Phase 7) | -- | AES-256 encryption key |
| `ENABLE_KAFKA` | no | `false` | Enable Kafka event streaming |
| `KAFKA_BOOTSTRAP_SERVERS` | no | `localhost:9092` | Kafka broker addresses |
| `LOG_LEVEL` | no | `INFO` | Logging level |
| `LOG_FORMAT` | no | `json` | `json` or `text` |
| `ASAHI_PORT` | no | `5000` | API server port |
| `ASAHI_HOST` | no | `0.0.0.0` | API server bind address |
| `ASAHI_WORKERS` | no | `4` | Uvicorn/Gunicorn workers |
| `RUN_INTEGRATION_TESTS` | no | `false` | Enable integration test suite |

### 8.2 Application Configuration (config.yaml)

```yaml
# config/config.yaml

app:
  name: asahi
  version: "2.0.0"
  environment: production  # development | staging | production
  debug: false

cache:
  tier1:
    enabled: true
    ttl_seconds: 86400          # 24 hours
    max_entries: 100000
    backend: redis              # dict | redis
  tier2:
    enabled: true
    ttl_seconds: 86400
    similarity_default_threshold: 0.85
    vector_db: pinecone         # inmemory | pinecone | weaviate
    embedding_provider: cohere  # cohere | openai | ollama
    embedding_model: embed-english-v3.0
    embedding_dimension: 1024
    top_k: 5
  tier3:
    enabled: true
    ttl_seconds: 86400

routing:
  default_mode: autopilot
  default_quality_threshold: 3.5
  default_latency_budget_ms: 300
  fallback_model: claude-3-5-sonnet

batching:
  enabled: false                # Phase 3
  min_batch_size: 2
  max_batch_size: 10
  max_wait_ms: 500
  latency_threshold_ms: 200

token_optimization:
  enabled: false                # Phase 4
  min_relevance_threshold: 0.3
  max_history_turns: 5

feature_store:
  enabled: false                # Phase 5
  provider: local               # feast | tecton | local
  timeout_ms: 200

observability:
  prometheus:
    enabled: true
    port: 9090
  logging:
    level: INFO
    format: json

security:
  api_key_required: false       # Phase 7
  encryption_at_rest: false     # Phase 7
  cors_origins: ["*"]
  rate_limit_per_minute: 100

tasks:
  summarization:
    quality_threshold: 3.5
    latency_budget_ms: 300
    semantic_threshold: 0.85
    cache_ttl_hours: 24
  reasoning:
    quality_threshold: 4.2
    latency_budget_ms: 500
    semantic_threshold: 0.92
    cache_ttl_hours: 12
  faq:
    quality_threshold: 3.0
    latency_budget_ms: 200
    semantic_threshold: 0.70
    cache_ttl_hours: 168
  coding:
    quality_threshold: 4.2
    latency_budget_ms: 500
    semantic_threshold: 0.95
    cache_ttl_hours: 4
  legal:
    quality_threshold: 4.5
    latency_budget_ms: 2000
    semantic_threshold: 0.92
    cache_ttl_hours: 720
```

### 8.3 Model Configuration (config/models.yaml)

```yaml
models:
  gpt-4-turbo:
    provider: openai
    api_key_env: OPENAI_API_KEY
    cost_per_1k_input_tokens: 0.010
    cost_per_1k_output_tokens: 0.030
    avg_latency_ms: 200
    quality_score: 4.6
    max_input_tokens: 128000
    max_output_tokens: 4096
    description: "High quality, expensive"

  claude-opus-4:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    cost_per_1k_input_tokens: 0.015
    cost_per_1k_output_tokens: 0.075
    avg_latency_ms: 180
    quality_score: 4.5
    max_input_tokens: 200000
    max_output_tokens: 4096
    description: "Highest quality Anthropic model"

  claude-3-5-sonnet:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    cost_per_1k_input_tokens: 0.003
    cost_per_1k_output_tokens: 0.015
    avg_latency_ms: 150
    quality_score: 4.1
    max_input_tokens: 200000
    max_output_tokens: 4096
    description: "Best cost/quality ratio"

  claude-3-5-haiku:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    cost_per_1k_input_tokens: 0.001
    cost_per_1k_output_tokens: 0.005
    avg_latency_ms: 80
    quality_score: 3.8
    max_input_tokens: 200000
    max_output_tokens: 4096
    description: "Ultra-fast, context generation"

  mistral-7b:
    provider: mistral
    api_key_env: MISTRAL_API_KEY
    cost_per_1k_input_tokens: 0.001
    cost_per_1k_output_tokens: 0.003
    avg_latency_ms: 120
    quality_score: 3.2
    max_input_tokens: 32000
    max_output_tokens: 2048
    description: "Cheapest option for simple tasks"
```

---

## 9. Configuration Loading Priority

```
1. Environment variables (highest priority -- overrides everything)
2. config/config.yaml (application settings)
3. config/models.yaml (model profiles)
4. Built-in defaults (lowest priority)
```

All configuration is validated by Pydantic on startup.  Invalid configuration prevents the application from starting and logs the exact validation errors.
