# Asahi Integration Roadmap

> **Purpose:** Close the gap between implemented components and the intended production pipeline.  
> **Current state:** Phases 1–6 components exist; only Tier 1 cache + basic routing are wired into the inference path.  
> **Target:** Full pipeline integration, global exception handling, and production-ready infrastructure.

---

## Implementation status (as of production build)

| Step | Description | Status |
|------|-------------|--------|
| Step 1 | Global exception handler | Done |
| Step 2 | Phase 2 pipeline (Tier 2/3, AdvancedRouter) | Done |
| Step 3 | Token optimization in pipeline | Done |
| Step 4 | Feature store (FeatureEnricher) in pipeline | Done |
| Step 5 | Batching (queue + scheduler + executor) | Done |
| Step 6 | Auth and governance (RBAC, policy/budget, audit) | Done |
| Step 7 | Infrastructure (PostgreSQL, Redis, Pinecone) | Done |
| Step 8 | Phase 8 Agent Swarm | Future |

See `docs/PRODUCTION_ROADMAP_DETAILED.md` for the unified production plan and remaining Phase 3–4 (GTM, pricing, onboarding, docs).

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Priority Order](#2-priority-order)
3. [Step 1: Global Exception Handler](#3-step-1-global-exception-handler)
4. [Step 2: Phase 2 Pipeline Integration](#4-step-2-phase-2-pipeline-integration)
5. [Step 3: Phase 4 Token Optimization Integration](#5-step-3-phase-4-token-optimization-integration)
6. [Step 4: Phase 5 Feature Store Integration](#6-step-4-phase-5-feature-store-integration)
7. [Step 5: Phase 3 Batching Integration](#7-step-5-phase-3-batching-integration)
8. [Step 6: Phase 7 Auth and Governance Wiring](#8-step-6-phase-7-auth-and-governance-wiring)
9. [Step 7: Infrastructure (DB, Redis, Pinecone)](#9-step-7-infrastructure-db-redis-pinecone)
10. [Step 8: Phase 8 Agent Swarm (Future)](#10-step-8-phase-8-agent-swarm-future)
11. [Dependency Graph](#11-dependency-graph)
12. [Estimated Effort](#12-estimated-effort)

---

## 1. Executive Summary

| Gap | Severity | Effort | Impact |
|-----|----------|--------|--------|
| Global exception handler | High | 0.5 day | Consistent error responses; no leaked tracebacks |
| Tier 2 + Tier 3 cache in optimizer | Critical | 3–5 days | 85–92% cost savings; semantic cache hits |
| AdvancedRouter (3 modes) in optimizer | High | 1–2 days | AUTOPILOT / GUIDED / EXPLICIT routing |
| Token optimization in path | High | 2–3 days | 20–30% token reduction |
| Feature store enrichment in path | Medium | 1–2 days | Context-aware prompts |
| Batching in path | Medium | 2–3 days | 40–60% cost reduction for eligible requests |
| Auth/RBAC on all endpoints | High | 2–3 days | Enterprise readiness |
| PostgreSQL, Redis, Pinecone | Critical | 1–2 weeks | Persistence; horizontal scaling |

---

## 2. Priority Order

```
Week 1:  Step 1 (exception handler) + Step 2 (Phase 2 pipeline)
Week 2:  Step 3 (token optimization) + Step 4 (feature store)
Week 3:  Step 5 (batching) + Step 6 (auth wiring)
Week 4+: Step 7 (infrastructure)
```

**Rationale:** Fix error handling first (low risk, high value). Then unlock the largest cost savings (Tier 2/3). Token optimization and feature store are quick wins. Batching and auth complete the pipeline. Infrastructure is last because it depends on a stable application layer.

---

## 3. Step 1: Global Exception Handler

### Problem

- Only three exceptions have handlers: `BudgetExceededError`, `PermissionDeniedError`, `ComplianceViolationError`.
- `ProviderError`, `NoModelsAvailableError`, `EmbeddingError`, `ObservabilityError`, etc. are not handled globally.
- Unhandled exceptions return 500 with a raw traceback or inconsistent JSON.

### Solution

Add two FastAPI exception handlers in `src/api/app.py`:

1. **`AsahiException` handler** — Catch all `AsahiException` subclasses. Map to appropriate HTTP status:
   - `NoModelsAvailableError`, `ProviderError` → 503
   - `ModelNotFoundError`, `ConfigurationError`, `FeatureConfigError` → 400
   - `EmbeddingError`, `VectorDBError`, `FeatureStoreError`, `ObservabilityError`, `BatchingError` → 502 or 503
   - Return consistent JSON: `{"error": "<type>", "message": "...", "request_id": "..."}`

2. **Generic `Exception` handler** — Catch any unhandled exception. Return 500 with a generic message (no traceback to client). Log full traceback server-side.

### Acceptance Criteria

- [ ] Every `AsahiException` subclass returns a consistent JSON error body.
- [ ] Unhandled `Exception` returns 500 with generic message; traceback only in logs.
- [ ] `request_id` included in error responses when available.
- [ ] No raw Python tracebacks exposed to API clients.

### Files to Modify

- `src/api/app.py` — Add `@app.exception_handler(AsahiException)` and `@app.exception_handler(Exception)`.

### Example Implementation

```python
@app.exception_handler(AsahiException)
async def asahi_exception_handler(request: Request, exc: AsahiException) -> Response:
    """Handle all AsahiException subclasses with consistent JSON."""
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Map exception types to HTTP status codes
    status_map = {
        NoModelsAvailableError: 503,
        ProviderError: 503,
        ModelNotFoundError: 400,
        ConfigurationError: 400,
        FeatureConfigError: 400,
        EmbeddingError: 502,
        VectorDBError: 502,
        FeatureStoreError: 502,
        ObservabilityError: 502,
        BatchingError: 502,
    }
    status_code = status_map.get(type(exc), 500)
    
    return Response(
        content=json.dumps({
            "error": exc.__class__.__name__.replace("Error", "").lower(),
            "message": str(exc),
            "request_id": request_id,
        }),
        status_code=status_code,
        media_type="application/json",
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> Response:
    """Catch-all handler for unhandled exceptions."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "Unhandled exception",
        extra={"request_id": request_id, "error": str(exc)},
        exc_info=True,
    )
    return Response(
        content=json.dumps({
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "request_id": request_id,
        }),
        status_code=500,
        media_type="application/json",
    )
```

---

## 4. Step 2: Phase 2 Pipeline Integration

### Problem

- `InferenceOptimizer` only checks Tier 1 (exact) cache.
- Tier 2 (SemanticCache) and Tier 3 (IntermediateCache + WorkflowDecomposer) are never called.
- Basic `Router` is used; `AdvancedRouter` (AUTOPILOT, GUIDED, EXPLICIT) is not.
- After inference, results are stored only in Tier 1, not in Tier 2 or Tier 3.

### Solution

Refactor `InferenceOptimizer.infer()` to implement the intended flow:

```
1. TIER 1: Exact match
   if exact_cache.get(prompt): return cached

2. TIER 2: Semantic similarity
   result = semantic_cache.get(query, task_type, cost_sensitivity, recompute_cost)
   if result.hit: return cached

3. TIER 3: Intermediate reuse (optional; for multi-step prompts)
   steps = workflow_decomposer.decompose(prompt, document_id)
   if steps and intermediate_cache can serve: return combined

4. ROUTE: AdvancedRouter (not basic Router)
   decision = advanced_router.select_model(constraints, mode, task_type, ...)

5. EXECUTE: Call provider

6. STORE: exact_cache.set(...); semantic_cache.set(...); intermediate_cache where applicable
```

### Dependencies

- `EmbeddingEngine` (needs `COHERE_API_KEY` or `OPENAI_API_KEY` for embeddings).
- `VectorDatabase` — Use `InMemoryVectorDB` for local dev; `PineconeVectorDB` when `PINECONE_*` env vars are set.
- `TaskTypeDetector` — For task_type when using AdvancedRouter.
- `ConstraintInterpreter` — For quality/latency preferences in GUIDED mode.

### Configuration

- Add `config.yaml` section for semantic cache: `similarity_threshold`, `top_k`, `ttl_seconds`.
- Add `config.yaml` section for Tier 3: `enable_tier3`, `workflow_task_types`.

### Acceptance Criteria

- [ ] "What is Python?" and "explain about Python?" produce a Tier 2 cache hit on the second query.
- [ ] AdvancedRouter supports `mode` from request (AUTOPILOT, GUIDED, EXPLICIT).
- [ ] Results stored in both Tier 1 and Tier 2 after inference.
- [ ] Graceful degradation: if embedding/vector DB fails, fall back to Tier 1 only.
- [ ] End-to-end latency overhead < 60 ms for 3-tier miss.

### Files to Modify

- `src/core/optimizer.py` — Inject SemanticCache, IntermediateCache, WorkflowDecomposer, AdvancedRouter; implement full flow.
- `src/api/app.py` — Pass mode/task_type/quality/latency from request body to optimizer.
- `src/api/schemas.py` — Add `routing_mode`, `task_type` to `InferRequest` if not present.
- `config/config.yaml` — Add semantic and Tier 3 settings.
- `src/config.py` — Add settings dataclasses for new sections.

### Example Flow

```python
# In InferenceOptimizer.infer()
# 1. Tier 1
cache_entry = self._exact_cache.get(prompt)
if cache_entry:
    return cached_result

# 2. Tier 2
semantic_result = self._semantic_cache.get(
    query=prompt,
    task_type=task_id or "general",
    cost_sensitivity="medium",
    recompute_cost=estimated_cost,
)
if semantic_result.hit:
    return semantic_cached_result

# 3. Tier 3 (if enabled and applicable)
if self._config.enable_tier3:
    steps = self._workflow_decomposer.decompose(prompt, document_id)
    if steps:
        intermediate_result = self._intermediate_cache.execute_workflow(...)
        if intermediate_result.all_hit:
            return combined_result

# 4. Route via AdvancedRouter
decision = self._advanced_router.select_model(
    constraints=constraints,
    mode=routing_mode,  # from request
    task_type=task_id,
)

# 5. Execute
response = self._execute_inference(decision.model_name, prompt)

# 6. Store in all tiers
self._exact_cache.set(...)
self._semantic_cache.set(...)
if steps:
    self._intermediate_cache.store_steps(...)
```

---

## 5. Step 3: Phase 4 Token Optimization Integration

### Problem

- `TokenOptimizer` exists but is never called before inference.
- Prompts are sent to the LLM unmodified, missing 20–30% token reduction.

### Solution

In `InferenceOptimizer.infer()`, before routing and execution:

1. Call `token_optimizer.optimize(prompt, system_prompt, history, examples, task_type, quality_preference)`.
2. Use `optimized_result.optimized_prompt` (or assembled parts) as the actual prompt sent to the model.
3. If `optimized_result.quality_risk == "high"`, optionally skip optimization or log a warning.
4. Pass `optimized_result.original_tokens` and `optimized_result.optimized_tokens` to tracking.

### Configuration

- `config.yaml` already has `optimization` section; ensure `max_quality_risk` is respected.

### Acceptance Criteria

- [ ] Token count is reduced for prompts with redundant context.
- [ ] Quality risk is assessed; high-risk cases are configurable (skip or warn).
- [ ] Metrics include token savings.

### Files to Modify

- `src/core/optimizer.py` — Inject TokenOptimizer; call before routing; use optimized prompt for inference.

### Example Integration

```python
# Before routing (after cache misses)
optimization_result = self._token_optimizer.optimize(
    prompt=prompt,
    system_prompt=None,
    history=None,
    examples=None,
    task_type=task_id or "general",
    quality_preference="medium",
)

if optimization_result.quality_risk == "high" and self._config.skip_high_risk_optimization:
    final_prompt = prompt  # Skip optimization
else:
    final_prompt = optimization_result.optimized_prompt

# Use final_prompt for routing and inference
```

---

## 6. Step 4: Phase 5 Feature Store Integration

### Problem

- `FeatureEnricher` exists but is never called.
- Prompts are not augmented with user/org context from the feature store.

### Solution

In `InferenceOptimizer.infer()`, before token optimization:

1. If `user_id` or `organization_id` is provided, call `feature_enricher.enrich(prompt, user_id, organization_id, task_type, context)`.
2. Use `enrichment_result.enriched_prompt` as the prompt for downstream steps.
3. If enrichment times out or fails, use original prompt (fallback_on_timeout).
4. Optionally record enrichment in FeatureMonitor for quality tracking.

### Configuration

- `config.yaml` already has `feature_store` section.

### Acceptance Criteria

- [ ] Enriched prompts include relevant user/org features when IDs are provided.
- [ ] Timeout does not block inference.
- [ ] FeatureMonitor tracks success/failure if wired.

### Files to Modify

- `src/core/optimizer.py` — Inject FeatureEnricher; call before token optimization when user_id/org_id present.

### Example Integration

```python
# At start of infer(), after cache checks
enriched_prompt = prompt
if user_id or organization_id:
    enrichment_result = self._feature_enricher.enrich(
        prompt=prompt,
        user_id=user_id,
        organization_id=organization_id,
        task_type=task_id or "general",
    )
    if enrichment_result.success:
        enriched_prompt = enrichment_result.enriched_prompt

# Use enriched_prompt for token optimization and inference
```

---

## 7. Step 5: Phase 3 Batching Integration

### Problem

- `BatchEngine`, `RequestQueue`, `BatchScheduler` exist but are not used.
- Every request is executed immediately; no batching of eligible requests.

### Solution

1. **Eligibility check:** Before inference, call `batch_engine.evaluate(prompt, task_type, model, latency_budget_ms)`. If `eligible`, enqueue instead of executing immediately.
2. **Request queue:** `RequestQueue.enqueue(QueuedRequest(...))` with batch group derived from task_type + model.
3. **Scheduler:** `BatchScheduler` runs in background; when batch is ready (size or deadline), execute via a batch-capable executor.
4. **Fallback:** If a request's deadline is approaching and batch is not ready, execute individually.

### Complexity

- Requires async or background execution model.
- Executor must support batch inference (e.g. multiple prompts in one API call if provider supports it, or parallel single calls).
- Higher effort than token/feature integration.

### Acceptance Criteria

- [ ] Eligible requests (e.g. summarization, faq, translation) are batched when possible.
- [ ] No request exceeds latency budget due to batching.
- [ ] Error in one batch request does not fail the entire batch.

### Files to Modify

- `src/core/optimizer.py` — Integrate BatchEngine, RequestQueue, BatchScheduler.
- `src/api/app.py` — May need async/background task for scheduler.

### Example Integration

```python
# In InferenceOptimizer.infer(), before cache checks
eligibility = self._batch_engine.evaluate(
    prompt=prompt,
    task_type=task_id or "general",
    model="preferred_model",  # from routing decision
    latency_budget_ms=latency_budget_ms,
)

if eligibility.eligible:
    # Enqueue for batching
    queued_request = QueuedRequest(...)
    self._request_queue.enqueue(queued_request)
    # Wait for batch execution or timeout
    return await wait_for_batch_result(queued_request)
else:
    # Execute immediately (existing flow)
    ...
```

---

## 8. Step 6: Phase 7 Auth and Governance Wiring

### Problem

- Auth, RBAC, audit, compliance components exist but may not be enforced on all endpoints.
- `/infer` and analytics endpoints may be unauthenticated.
- No tenant isolation in cache keys or metrics.

### Solution

1. **Auth middleware:** Ensure `AuthMiddleware` runs on all protected routes. Extract `user_id`, `org_id` from API key or token.
2. **RBAC:** Before sensitive operations, call `governance.check_permission(user_id, org_id, action)`.
3. **Policy enforcement:** Before inference, call `governance.enforce_policy(request, org_policy)` and `governance.check_budget(org_id, estimated_cost)`.
4. **Audit:** Log all inference, policy changes, and access events via `AuditLogger`.
5. **Tenant isolation:** Prefix cache keys and vector DB namespace with `org_id` when multi-tenancy is enabled.

### Configuration

- `config.yaml` governance section; `auth_api_key_required` to toggle strictness.

### Acceptance Criteria

- [ ] All inference and analytics endpoints require valid API key when `auth_api_key_required=true`.
- [ ] Budget and policy checks block non-compliant requests.
- [ ] Audit log contains all required events.
- [ ] Cache and metrics are scoped by org when multi-tenant.

### Files to Modify

- `src/api/app.py` — Wire auth middleware; add dependency on governance for protected routes.
- `src/core/optimizer.py` — Accept org_id; pass to cache key generation and policy checks.

### Example Integration

```python
# In app.py, before routes
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if settings.governance.auth_api_key_required:
        auth_result = auth_middleware.authenticate(request)
        if not auth_result.authenticated:
            return Response(status_code=401, ...)
        request.state.user_id = auth_result.user_id
        request.state.org_id = auth_result.org_id

# In optimizer.infer()
org_id = getattr(request.state, "org_id", None)
if org_id:
    # Check policy
    allowed, reason = governance.enforce_policy(request, org_policy)
    if not allowed:
        raise PermissionDeniedError(reason)
    
    # Check budget
    budget_ok, reason = governance.check_budget(org_id, estimated_cost)
    if not budget_ok:
        raise BudgetExceededError(reason)
    
    # Use org-scoped cache keys
    cache_key = f"{org_id}:{hashlib.md5(prompt).hexdigest()}"
```

---

## 9. Step 7: Infrastructure (DB, Redis, Pinecone)

### Problem

- All state is in-memory or JSONL/JSON files.
- No persistence across restarts; no horizontal scaling.
- Vector DB is in-memory; production needs Pinecone.

### Solution

1. **PostgreSQL:** For tenants, users, API keys, policies, audit log metadata. Use SQLAlchemy or asyncpg; add Alembic migrations.
2. **Redis:** For distributed Tier 1 cache (replace in-memory dict). Key format: `{org_id}:{cache_key}`.
3. **Pinecone:** For Tier 2 vector store. Create index; use `PineconeVectorDB` when `PINECONE_API_KEY` is set.
4. **Config:** Add `DatabaseSettings`, `RedisSettings`, `PineconeSettings` to `src/config.py`. Load from env.

### Order

1. PostgreSQL + Alembic (schema for governance, audit).
2. Redis (cache backend).
3. Pinecone (vector backend).

### Acceptance Criteria

- [ ] Tier 1 cache uses Redis when `REDIS_URL` is set.
- [ ] Tier 2 uses Pinecone when `PINECONE_*` is set.
- [ ] API keys, tenants, policies stored in PostgreSQL.
- [ ] Multiple API instances can share cache and state.

### Files to Create/Modify

- `src/db/` — Database connection, repositories.
- `src/cache/redis_backend.py` — Redis implementation of Cache interface.
- `src/embeddings/vector_store.py` — Ensure PineconeVectorDB is complete and config-driven.
- `config/config.yaml` — Add database, redis, pinecone sections.
- `alembic/` — Migrations.

### Configuration Example

```yaml
# config/config.yaml
database:
  url: ${DATABASE_URL}
  pool_size: 10
  echo: false

redis:
  url: ${REDIS_URL}
  ttl_seconds: 86400
  key_prefix: "asahi"

pinecone:
  api_key_env: PINECONE_API_KEY
  environment: ${PINECONE_ENVIRONMENT}
  index_name: asahi-vectors
  dimension: 1024
  metric: cosine
```

---

## 10. Step 8: Phase 8 Agent Swarm (Future)

### Problem

- No `src/agents/` module. Phase 8 is not started.

### Solution

- Defer until Phases 2–7 integration is complete and stable.
- Follow `docs/phase8_requirements.md` when starting.
- Components: AgentContextualCache, InterAgentMessageCompressor, AgentStateManagement, AgentSpecializationRouter, AgentCostAttributor, AgentSwarmOrchestrator, AgentMeshMonitor, AgentFailureRecovery.

### Estimated Effort

- 14 weeks per original roadmap.

---

## 11. Dependency Graph

```
Step 1 (Exception handler)
    └── No dependencies

Step 2 (Phase 2 pipeline)
    ├── EmbeddingEngine (COHERE/OPENAI key)
    ├── VectorDatabase (InMemory or Pinecone)
    ├── SemanticCache, IntermediateCache, WorkflowDecomposer
    ├── AdvancedRouter, TaskTypeDetector, ConstraintInterpreter
    └── Config for semantic/Tier3

Step 3 (Token optimization)
    └── TokenOptimizer (already has deps)

Step 4 (Feature store)
    └── FeatureEnricher, FeatureStoreClient (already has deps)

Step 5 (Batching)
    ├── BatchEngine, RequestQueue, BatchScheduler
    └── Async/background execution model

Step 6 (Auth/Governance)
    ├── AuthMiddleware, GovernanceEngine
    ├── AuditLogger, ComplianceManager
    └── Step 7 (PostgreSQL) for persistence

Step 7 (Infrastructure)
    ├── PostgreSQL
    ├── Redis
    └── Pinecone
```

---

## 12. Estimated Effort

| Step | Effort | Dependencies |
|------|--------|--------------|
| 1. Global exception handler | 0.5 day | None |
| 2. Phase 2 pipeline | 3–5 days | Embedding + vector DB |
| 3. Token optimization | 2–3 days | None |
| 4. Feature store | 1–2 days | None |
| 5. Batching | 2–3 days | None |
| 6. Auth wiring | 2–3 days | Optional: DB for keys |
| 7. Infrastructure | 1–2 weeks | Cloud accounts, Docker |
| **Total (Steps 1–6)** | **~2–3 weeks** | |
| **Total (with Step 7)** | **~4–5 weeks** | |

---

## 13. Testing Strategy

Each integration step should include:

- **Unit tests** — Verify the new component wiring in isolation.
- **Integration tests** — End-to-end request flow with mocked dependencies.
- **Regression tests** — Ensure existing functionality still works.
- **Performance tests** — Verify latency overhead targets are met.

### Example Test Structure

```python
# tests/integration/test_full_pipeline.py
def test_tier2_cache_hit_on_semantically_similar_query():
    """Verify Tier 2 cache serves semantically similar queries."""
    optimizer = InferenceOptimizer(...)  # with SemanticCache wired
    
    # First query
    result1 = optimizer.infer("What is Python?")
    assert result1.cache_hit is False
    
    # Semantically similar query
    result2 = optimizer.infer("explain about Python?")
    assert result2.cache_hit is True
    assert result2.cost == 0.0  # Tier 2 hit
```

---

## 14. Rollout Plan

### Phase A: Foundation (Week 1)
- Step 1: Exception handler
- Step 2: Phase 2 pipeline (Tier 2 + AdvancedRouter)

### Phase B: Optimization (Week 2)
- Step 3: Token optimization
- Step 4: Feature store

### Phase C: Advanced Features (Week 3)
- Step 5: Batching
- Step 6: Auth wiring

### Phase D: Infrastructure (Week 4+)
- Step 7: PostgreSQL, Redis, Pinecone

### Rollback Strategy

- Each step should be **feature-flagged** via config.
- If a step causes issues, disable via config without code changes.
- Example: `config.yaml` → `cache.tier2_enabled: false` → falls back to Tier 1 only.

---

## 15. Success Metrics

After completing Steps 1–6, measure:

| Metric | Target | Measurement |
|--------|--------|-------------|
| Cost savings | 85–92% | Compare baseline vs optimized |
| Cache hit rate | 75–90% | Tier 1 + Tier 2 combined |
| Token reduction | 20–30% | Average across optimized prompts |
| Error response consistency | 100% | All errors return JSON with error/message/request_id |
| Latency overhead | < 60 ms | Cache operations (all tiers miss) |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-02-13 | — | Initial integration roadmap |
