# Integration guide

Step-by-step guide for developers integrating with the Asahi inference cost optimizer.

## Overview

Asahi sits between your application and LLM providers (OpenAI, Anthropic). You send prompts (or OpenAI-format messages) to Asahi; it applies caching, routing, and cost optimization, then returns the response. You can use the native `POST /infer` API or the OpenAI-compatible `POST /v1/chat/completions` endpoint.

## Step 1: Obtain credentials

1. **API key:** Use [Quick start](QUICK_START.md) — either self-serve signup (`POST /signup`) or an admin-created key (`POST /governance/api-keys`).
2. **Base URL:** Your deployment URL (e.g. `https://api.asahi.example.com`). For OpenAI-style clients, use `https://api.asahi.example.com/v1` as the base URL so that `/chat/completions` resolves correctly.

## Step 2: Authenticate requests

Send the API key on every request (except `/health`, `/docs`, `/openapi.json`):

```
Authorization: Bearer YOUR_API_KEY
```

Requests without a valid key receive `401 Unauthorized`.

## Step 3: Choose the API shape

| Use case | Endpoint | Request shape |
|----------|----------|----------------|
| Drop-in for existing OpenAI code | `POST /v1/chat/completions` | `messages`, `model`, `max_tokens` (OpenAI format) |
| Full control (budgets, routing, task_id) | `POST /infer` | `prompt`, `routing_mode`, `latency_budget_ms`, `cost_budget`, etc. |

Both return the LLM response; `/infer` also returns `cost`, `model_used`, `cache_hit`, `cache_tier`, `routing_reason`, and optional cost/savings fields.

## Step 4: Routing modes (`/infer`)

- **`autopilot`** — Asahi picks the cheapest model that meets quality/latency (default).
- **`guided`** — You set `quality_preference` and/or `latency_preference`; Asahi chooses within those.
- **`explicit`** — You set `model_override`; Asahi uses that model (subject to org policy).

For `POST /v1/chat/completions`, omitting `model` or using a generic name (e.g. `asahi`) uses autopilot; sending a specific `model` uses explicit routing for that model.

## Step 5: Organisation and caching

- Send `organization_id` (or rely on the one from your API key) so cache and usage are namespaced per org.
- Cache is three-tier: exact match (Tier 1), semantic similarity (Tier 2), intermediate workflow (Tier 3). Repeated or similar prompts reduce cost and latency.

## Step 6: Check metrics and usage

- **Dashboard / cost:** `GET /metrics`, `GET /analytics/cost-summary?period=24h`, `GET /analytics/recent-inferences`.
- **Per-org usage (admin):** `GET /governance/usage?org_id=...&period=day|month`.

See [API_CONTRACT.md](API_CONTRACT.md) for the full list of endpoints, request/response fields, and scopes.

## Example: end-to-end with Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://your-asahi-api.com/v1",
    api_key="YOUR_ASAHI_API_KEY",
)

# Autopilot: Asahi picks the model
r = client.chat.completions.create(
    model="asahi",
    messages=[{"role": "user", "content": "Explain async/await in Python."}],
    max_tokens=512,
)
print(r.choices[0].message.content)
print(r.usage)
```

## Example: end-to-end with curl (`/infer`)

```bash
curl -X POST https://your-asahi-api.com/infer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ASAHI_API_KEY" \
  -d '{
    "prompt": "Explain async/await in Python.",
    "routing_mode": "autopilot",
    "organization_id": "your-org-id",
    "latency_budget_ms": 5000
  }'
```

## Troubleshooting

- **401:** Missing or invalid `Authorization: Bearer ...` header.
- **403:** API key does not have the required scope (e.g. `infer` for `/infer`, `analytics` for analytics routes).
- **429:** Rate limit exceeded; retry with backoff.
- **503:** Service or dependency (e.g. Redis, DB) unavailable; check `/health`.

For local development and testing, see [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md).
