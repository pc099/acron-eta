# Load testing Asahi API

Use this to validate p95 latency and throughput (Phase 1.2 targets: p95 &lt;100 ms end-to-end, 500+ req/s per instance under load).

## Prerequisites

- API running (e.g. `uvicorn src.api.app:create_app --factory`)
- Optional: valid API key for `/infer` if auth is enabled (set `Authorization: Bearer <key>` or disable auth for testing)

## Using `wrk`

```bash
# Install: https://github.com/wg/wrk

# Health check (no auth)
wrk -t4 -c50 -d30s http://localhost:8000/health

# Infer endpoint (POST). Create a Lua script so wrk sends JSON body:
# save as infer.lua:
#   wrk.method = "POST"
#   wrk.body   = '{"prompt":"Hello world","routing_mode":"autopilot"}'
#   wrk.headers["Content-Type"] = "application/json"
wrk -t4 -c50 -d30s -s infer.lua http://localhost:8000/infer
```

Interpret results: `Latency` section shows distribution; aim for p95 &lt;100 ms and no failed requests under sustained load.

## Using Locust (optional)

```bash
pip install locust
locust -f locustfile.py --host=http://localhost:8000
# Open http://localhost:8089, set users and spawn rate, run test
```

See `locustfile.py` in the project root for a minimal `/infer` and `/health` user flow. After the run, check "Charts" for latency percentiles and RPS.

## Notes

- The hot path runs `optimizer.infer` in a thread pool (`asyncio.to_thread`) so the event loop stays responsive under concurrency.
- LLM provider clients (OpenAI, Anthropic) are reused per process for connection pooling.
- For cache-hit heavy tests, repeat the same prompt to exercise Tier 1; vary prompts for cache-miss and throughput.
