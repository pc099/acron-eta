# Repo Map

Use this file to localize work before changing code.

## Split Architecture

- `src/`: original optimizer implementation with routing, multi-tier caching, embeddings, observability, and governance modules.
- `backend/`: production FastAPI backend with DB and Redis integration.
- `frontend/`: Next.js dashboard.
- `sdk/`: Python client.

Do not assume a change belongs in both `src/` and `backend/`. Decide which stack the user is asking about.

## Highest-Leverage Files

### End-to-end request path

- `src/core/optimizer.py`: orchestration for cache -> route -> infer -> track.
- `backend/app/core/optimizer.py`: production optimizer variant if the request targets the SaaS backend.

### Routing

- `src/routing/router.py`: core model selection logic.
- `src/routing/task_detector.py`: task classification.
- `src/routing/constraints.py`: quality, latency, and budget interpretation.
- `config/models.yaml`: model profiles, latency, quality, and pricing metadata.

### Caching and reuse

- `src/cache/exact.py`: Tier 1 exact-match cache.
- `src/cache/semantic.py`: Tier 2 semantic cache.
- `src/cache/intermediate.py`: Tier 3 intermediate cache.
- `src/cache/workflow.py`: workflow decomposition and reusable step keys.
- `src/embeddings/`: embedding engine, similarity, thresholds, vector storage.

### Optimization and throughput

- `src/optimization/optimizer.py`: prompt and token optimization.
- `src/batching/`: request queue, scheduler, and batch eligibility.
- `src/features/`: enrichment that changes prompt context before routing or inference.

### Observability and governance

- `src/tracking/tracker.py`: inference event logging.
- `src/observability/analytics.py`: cost and latency analytics.
- `src/governance/`: policy, budget, audit, and multi-tenant controls.

### Production backend surface

- `backend/app/api/`: external endpoints and request contracts.
- `backend/app/services/cache.py`: runtime cache service wiring.
- `backend/app/db/models.py`: persistence model shape.

## Fast Triage

If the problem is about:

- wrong model choice: inspect routing, task detection, and model metadata.
- low cache hit rate: inspect cache keys, thresholding, embeddings, and workflow decomposition.
- poor latency: inspect provider call path, retries, batching, async boundaries, and cache misses.
- unexpected cost: inspect routing policy, output token inflation, cache bypass, and analytics attribution.
- novel idea needed: inspect the current bottleneck first, then open `idea-patterns.md`.
