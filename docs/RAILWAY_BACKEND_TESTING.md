# Railway Backend Testing Guide

How to test the Asahi backend **before** and **after** deploying to Railway: local checks, smoke testing the live URL, and verifying Redis/Postgres in production.

For automated unit/integration tests (pytest), see [BACKEND_TESTING_GUIDE.md](BACKEND_TESTING_GUIDE.md). For deployment steps, see [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md).

---

## Table of Contents

1. [Before Deploy: Local Checks](#1-before-deploy-local-checks)
2. [After Deploy: Smoke Test the Live API](#2-after-deploy-smoke-test-the-live-api)
3. [Testing with Authentication](#3-testing-with-authentication)
4. [Smoke Test Script (Optional)](#4-smoke-test-script-optional)
5. [Verifying Redis and Postgres on Railway](#5-verifying-redis-and-postgres-on-railway)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Before Deploy: Local Checks

Run the test suite and a quick local server check so the same code works on Railway.

### Run the test suite

```bash
cd d:\claude\asahi
pip install -r requirements.txt
pytest -v
```

Optional: run only API and core tests for a fast pre-deploy check:

```bash
pytest tests/api/ tests/core/ tests/test_acceptance.py -v
```

### Simulate Railway start (optional)

Railway sets `PORT` and runs uvicorn. Locally you can mimic that:

```bash
# Windows (PowerShell)
$env:PORT=8000; python -m uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port $env:PORT

# Linux/macOS
PORT=8000 python -m uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port $PORT
```

Then open `http://localhost:8000/health` — you should see `{"status":"healthy",...}`.

### Env checklist before deploy

Confirm these are set in the **Railway** Asahi service (Variables):

| Variable | Required for |
|----------|----------------|
| `REDIS_URL` | Tier 1 cache (reference from Redis service) |
| `DATABASE_URL` | API keys, orgs (reference from Postgres service) |
| `OPENAI_API_KEY` | Inference |
| `ANTHROPIC_API_KEY` | Inference |
| `COHERE_API_KEY` | Tier 2 semantic cache |
| `PORT` | Set by Railway — do not override |

Optional: `ASAHI_ENCRYPTION_KEY`, `ASAHI_AUTH_API_KEY_REQUIRED`, `PINECONE_API_KEY`. See [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md#6-required-environment-variables).

---

## 2. After Deploy: Smoke Test the Live API

Replace `https://YOUR-RAILWAY-URL.up.railway.app` with your actual Railway-generated domain (e.g. from **Settings → Networking → Generate Domain**).

### Health check

```bash
curl https://YOUR-RAILWAY-URL.up.railway.app/health
```

Expected: `200` and JSON with `"status": "healthy"` and `components` (cache, router, registry, etc.).

### List models

```bash
curl https://YOUR-RAILWAY-URL.up.railway.app/models
```

Expected: `200` and a list of models with pricing/quality.

### Inference (no auth)

If **API key auth is not required** (`ASAHI_AUTH_API_KEY_REQUIRED` is not `true`):

```bash
curl -X POST https://YOUR-RAILWAY-URL.up.railway.app/infer \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"What is Python?\"}"
```

Expected: `200` and JSON with `response`, `model_used`, `cost`, `cache_hit`, etc.

### Metrics

```bash
curl https://YOUR-RAILWAY-URL.up.railway.app/metrics
```

Expected: `200` and JSON with `requests`, `total_cost`, `cache_hit_rate`, etc.

### OpenAPI docs

In a browser open:

- **Swagger UI:** `https://YOUR-RAILWAY-URL.up.railway.app/docs`
- **ReDoc:** `https://YOUR-RAILWAY-URL.up.railway.app/redoc`

Confirm the docs load and show `/health`, `/infer`, `/metrics`, `/models`.

---

## 3. Testing with Authentication

If `ASAHI_AUTH_API_KEY_REQUIRED=true`, all non-health requests must include an API key.

### Get an API key

- Sign up via the frontend (if connected), or
- Create via backend (e.g. admin script or `POST /governance/api-keys` if that endpoint exists), or
- Insert directly in Postgres (see your auth implementation).

### Call /infer with the key

```bash
curl -X POST https://YOUR-RAILWAY-URL.up.railway.app/infer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d "{\"prompt\": \"What is Python?\"}"
```

Without a valid key you should get `401 Unauthorized`.

### Call /metrics with the key

```bash
curl https://YOUR-RAILWAY-URL.up.railway.app/metrics \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

## 4. Smoke Test Script (Optional)

Save as `scripts/smoke_test_railway.sh` (Linux/macOS) or run the PowerShell equivalent. Replace `BASE_URL` and optionally `API_KEY`.

**Bash (Linux/macOS):**

```bash
#!/bin/bash
BASE_URL="${1:-https://YOUR-RAILWAY-URL.up.railway.app}"
API_KEY="${2:-}"

echo "Smoke testing: $BASE_URL"

# Health
echo -n "GET /health ... "
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/health")
[ "$code" = "200" ] && echo "OK ($code)" || echo "FAIL ($code)"

# Models (no auth)
echo -n "GET /models ... "
code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/models")
[ "$code" = "200" ] && echo "OK ($code)" || echo "FAIL ($code)"

# Infer
echo -n "POST /infer ... "
if [ -n "$API_KEY" ]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/infer" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $API_KEY" \
    -d '{"prompt":"Hi"}')
else
  code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/infer" \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Hi"}')
fi
[ "$code" = "200" ] && echo "OK ($code)" || echo "FAIL ($code)"

# Metrics
echo -n "GET /metrics ... "
if [ -n "$API_KEY" ]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $API_KEY" "$BASE_URL/metrics")
else
  code=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/metrics")
fi
[ "$code" = "200" ] && echo "OK ($code)" || echo "FAIL ($code)"

echo "Done."
```

Usage:

```bash
chmod +x scripts/smoke_test_railway.sh
./scripts/smoke_test_railway.sh
./scripts/smoke_test_railway.sh https://your-app.up.railway.app
./scripts/smoke_test_railway.sh https://your-app.up.railway.app your-api-key
```

**PowerShell (Windows):**

```powershell
param(
  [string]$BaseUrl = "https://YOUR-RAILWAY-URL.up.railway.app",
  [string]$ApiKey = ""
)

Write-Host "Smoke testing: $BaseUrl"

$headers = @{ "Content-Type" = "application/json" }
if ($ApiKey) { $headers["Authorization"] = "Bearer $ApiKey" }

@(
  @{ Method = "GET"; Path = "/health"; Auth = $false },
  @{ Method = "GET"; Path = "/models"; Auth = $false },
  @{ Method = "POST"; Path = "/infer"; Body = '{"prompt":"Hi"}'; Auth = $true },
  @{ Method = "GET"; Path = "/metrics"; Auth = $true }
) | ForEach-Object {
  $uri = $BaseUrl + $_.Path
  $h = if ($_.Auth -and $ApiKey) { $headers } else { @{ "Content-Type" = "application/json" } }
  try {
    if ($_.Method -eq "POST") {
      $r = Invoke-WebRequest -Uri $uri -Method POST -Headers $h -Body $_.Body -UseBasicParsing
    } else {
      $r = Invoke-WebRequest -Uri $uri -Method GET -Headers $h -UseBasicParsing
    }
    Write-Host "$($_.Method) $($_.Path) ... OK ($($r.StatusCode))"
  } catch {
    Write-Host "$($_.Method) $($_.Path) ... FAIL"
  }
}
```

Run: `.\scripts\smoke_test_railway.ps1` or `.\scripts\smoke_test_railway.ps1 -BaseUrl "https://..." -ApiKey "..."`

---

## 5. Verifying Redis and Postgres on Railway

- **Redis:** After a few `POST /infer` calls, call `GET /metrics`. You should see non-zero `cache_size` and, on repeated same prompt, `cache_hit: true` in the infer response. That confirms the app is using Railway’s Redis.
- **Postgres:** If auth is on, API keys are stored in Postgres. Creating a key (e.g. via signup or admin) and then using it for `/infer` and `/metrics` confirms the app is using Railway’s Postgres.

If you see connection errors in Railway logs, check that `REDIS_URL` and `DATABASE_URL` are **variable references** to the Redis and Postgres services, not copied strings from another environment.

---

## 6. Troubleshooting

| Issue | What to check |
|-------|----------------|
| **Health returns 5xx or timeout** | Railway service not running; check Deployments and build logs. Ensure start command uses `$PORT` (e.g. `sh -c 'uvicorn ... --port ${PORT:-8000}'`). |
| **502 Bad Gateway** | App may be crashing on startup. Check Railway logs for Python tracebacks; verify env vars (e.g. `DATABASE_URL`, `REDIS_URL`) are set and valid. |
| **401 on /infer or /metrics** | Auth is required. Send `Authorization: Bearer <api_key>`. If auth is not intended, set `ASAHI_AUTH_API_KEY_REQUIRED` to `false` or leave unset. |
| **Redis/Postgres connection errors** | In Railway Variables, use **Variable Reference** from the Redis/Postgres services for `REDIS_URL` and `DATABASE_URL`. |
| **Cohere/OpenAI/Anthropic errors** | Ensure the corresponding `*_API_KEY` variables are set in the Asahi service and are valid. |

More deployment details: [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md#11-troubleshooting).

---

## Quick reference

| Step | Command or URL |
|------|----------------|
| Local tests before deploy | `pytest tests/api/ tests/core/ tests/test_acceptance.py -v` |
| Health (live) | `curl https://YOUR-URL/health` |
| Infer (no auth) | `curl -X POST https://YOUR-URL/infer -H "Content-Type: application/json" -d '{"prompt":"Hi"}'` |
| Infer (with auth) | Add `-H "Authorization: Bearer YOUR_API_KEY"` |
| Docs | `https://YOUR-URL/docs` |

Related docs:

- [RAILWAY_DEPLOYMENT.md](RAILWAY_DEPLOYMENT.md) — deploy and env setup  
- [BACKEND_TESTING_GUIDE.md](BACKEND_TESTING_GUIDE.md) — pytest and coverage  
- [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md) — manual local API testing  
