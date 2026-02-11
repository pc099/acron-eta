# Phase 1: MVP and Basic Optimization -- Component Specification

> **Status**: COMPLETE  
> **Timeline**: 8 weeks  
> **Cost savings target**: 58%  
> **Cache hit rate**: 25-35% (exact match only)  
> **Quality floor**: 4.0 / 5.0  
> **Test coverage gate**: 28/28 tests passing  

---

## 1. Design Principles (apply to every component)

- **Zero hardcoded values** -- every threshold, TTL, model name, and pricing number lives in configuration (YAML / env var / Pydantic model).
- **Type hints on every function and method** -- enforced by `mypy --strict`.
- **Docstrings on every public class and function** -- Google-style, including Args, Returns, Raises.
- **Structured logging** -- every significant operation emits a JSON log line with `request_id` context.
- **Error handling** -- all external calls (LLM APIs, file I/O) wrapped in try/except with specific exception types; never bare `except`.
- **Single Responsibility** -- each module owns one concern; no module exceeds 600 lines.
- **Dependency Injection** -- components receive their collaborators via constructor; no global singletons.

---

## 2. Component 1: Model Registry

### 2.1 Purpose

Single source of truth for every LLM model the platform can route to.  Stores pricing, latency, quality, and capability metadata.  All other components query this registry -- they never hard-code model information.

### 2.2 File

`src/models.py` (~180 lines)

### 2.3 Public Classes

#### `ModelProfile` (Pydantic BaseModel)

| Field | Type | Validation | Description |
|-------|------|------------|-------------|
| `name` | `str` | required, unique | Canonical model identifier, e.g. `claude-3-5-sonnet` |
| `provider` | `Literal["openai","anthropic","mistral","local"]` | required | Which SDK/adapter to use |
| `api_key_env` | `str` | required | Env var name holding the secret, e.g. `ANTHROPIC_API_KEY` |
| `cost_per_1k_input_tokens` | `float` | >= 0 | Dollar cost per 1 000 input tokens |
| `cost_per_1k_output_tokens` | `float` | >= 0 | Dollar cost per 1 000 output tokens |
| `avg_latency_ms` | `int` | > 0 | Expected p50 latency in milliseconds |
| `quality_score` | `float` | 0.0 -- 5.0 | Benchmark quality rating |
| `max_input_tokens` | `int` | > 0 | Maximum context window |
| `max_output_tokens` | `int` | > 0 | Maximum generation length |
| `description` | `str` | optional | Human-readable note |
| `availability` | `Literal["available","degraded","unavailable"]` | default `available` | Runtime health status |

#### `ModelRegistry`

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, config_path: Optional[Path] = None)` | Load models from YAML config or built-in defaults |
| `add` | `(self, profile: ModelProfile) -> None` | Register or update a model |
| `get` | `(self, name: str) -> ModelProfile` | Return profile; raise `ModelNotFoundError` if missing |
| `remove` | `(self, name: str) -> None` | De-register a model |
| `all` | `(self) -> List[ModelProfile]` | Return all registered profiles |
| `filter` | `(self, min_quality: float, max_latency_ms: int) -> List[ModelProfile]` | Return profiles meeting constraints |
| `load_from_yaml` | `(self, path: Path) -> None` | Parse YAML file and register all models |
| `to_dict` | `(self) -> Dict[str, Any]` | Serialize registry for API responses |

### 2.4 Internal State

- `_models: Dict[str, ModelProfile]` -- keyed by model `name`.

### 2.5 Configuration

```yaml
# config/models.yaml
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
  claude-opus-4:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    cost_per_1k_input_tokens: 0.015
    cost_per_1k_output_tokens: 0.075
    avg_latency_ms: 180
    quality_score: 4.5
    max_input_tokens: 200000
    max_output_tokens: 4096
  claude-3-5-sonnet:
    provider: anthropic
    api_key_env: ANTHROPIC_API_KEY
    cost_per_1k_input_tokens: 0.003
    cost_per_1k_output_tokens: 0.015
    avg_latency_ms: 150
    quality_score: 4.1
    max_input_tokens: 200000
    max_output_tokens: 4096
```

### 2.6 Error Handling

| Scenario | Exception | Behaviour |
|----------|-----------|-----------|
| Model name not found | `ModelNotFoundError(KeyError)` | Raise with message including the requested name |
| YAML parse failure | `ConfigurationError(ValueError)` | Raise with file path and parse error detail |
| Duplicate registration | Log warning, overwrite existing | |
| Invalid profile fields | Pydantic `ValidationError` | Propagate with field-level detail |

### 2.7 Testing Requirements

- Unit: 8+ tests covering add, get, remove, filter, YAML load, validation failures, serialisation.
- Edge: empty registry, filter returning zero results, duplicate names.
- Performance: registry with 50 models -- `filter` completes in < 1 ms.

---

## 3. Component 2: Routing Engine

### 3.1 Purpose

Given a set of constraints (minimum quality, maximum latency, optional cost budget), select the single most cost-efficient model from the registry.

### 3.2 File

`src/routing.py` (~250 lines)

### 3.3 Public Classes

#### `RoutingConstraints` (Pydantic BaseModel)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `quality_threshold` | `float` | `3.5` | Minimum acceptable quality score |
| `latency_budget_ms` | `int` | `300` | Maximum acceptable latency |
| `cost_budget` | `Optional[float]` | `None` | Maximum dollar cost per request (if provided) |

#### `RoutingDecision` (Pydantic BaseModel)

| Field | Type | Description |
|-------|------|-------------|
| `model_name` | `str` | Selected model |
| `score` | `float` | Computed quality/cost score |
| `reason` | `str` | Human-readable explanation |
| `candidates_evaluated` | `int` | Number of models that passed the filter |
| `fallback_used` | `bool` | True if no model passed filters and we fell back to highest quality |

#### `Router`

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, registry: ModelRegistry)` | Inject model registry |
| `select_model` | `(self, constraints: RoutingConstraints) -> RoutingDecision` | Main entry point; runs filter-score-select |
| `_filter` | `(self, constraints: RoutingConstraints) -> List[ModelProfile]` | Keep models meeting quality AND latency thresholds |
| `_score` | `(self, candidates: List[ModelProfile]) -> List[Tuple[ModelProfile, float]]` | Compute quality/cost ratio for each candidate |
| `_select` | `(self, scored: List[Tuple[ModelProfile, float]]) -> Tuple[ModelProfile, float]` | Pick highest score |

### 3.4 Algorithm (pseudocode)

```
function select_model(constraints):
    candidates = registry.filter(
        min_quality=constraints.quality_threshold,
        max_latency_ms=constraints.latency_budget_ms
    )
    
    if cost_budget is set:
        candidates = [m for m in candidates if avg_cost(m) <= cost_budget]
    
    if candidates is empty:
        log.warning("No models pass constraints; falling back to highest quality")
        best = model with max quality_score from registry.all()
        return RoutingDecision(model=best, fallback_used=True, reason="fallback")
    
    scored = []
    for model in candidates:
        avg_cost = (model.cost_per_1k_input + model.cost_per_1k_output) / 2
        score = model.quality_score / avg_cost
        scored.append((model, score))
    
    best = max(scored, key=lambda x: x[1])
    return RoutingDecision(
        model_name=best[0].name,
        score=best[1],
        reason=f"Best quality/cost ratio among {len(candidates)} candidates",
        candidates_evaluated=len(candidates),
        fallback_used=False
    )
```

### 3.5 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Registry is empty (zero models) | Raise `NoModelsAvailableError` |
| All models filtered out | Fallback to highest quality model; set `fallback_used=True` |
| Cost budget filters all out | Same fallback logic |

### 3.6 Testing Requirements

- Unit: 10+ tests covering happy path, fallback, cost budget filter, tie-breaking, single model, all models filtered.
- Property-based: random constraints against random model sets always return a valid decision or raise `NoModelsAvailableError`.

---

## 4. Component 3: Exact-Match Cache

### 4.1 Purpose

Store and retrieve inference responses keyed by MD5 hash of the user query.  Ignore system prompts.  Enforce TTL-based expiration.  Track hit/miss statistics.

### 4.2 File

`src/cache.py` (~180 lines)

### 4.3 Public Classes

#### `CacheEntry` (Pydantic BaseModel)

| Field | Type | Description |
|-------|------|-------------|
| `cache_key` | `str` | MD5 hex digest |
| `query` | `str` | Original user query |
| `response` | `str` | Cached response text |
| `model` | `str` | Model that produced the response |
| `cost` | `float` | Original inference cost |
| `created_at` | `datetime` | When entry was stored |
| `expires_at` | `datetime` | When entry becomes stale |
| `access_count` | `int` | Number of times this entry has been served |

#### `Cache`

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, ttl_seconds: int = 86400)` | Initialise with configurable TTL (default 24 h) |
| `generate_key` | `(self, query: str) -> str` | `hashlib.md5(query.encode()).hexdigest()` |
| `get` | `(self, query: str) -> Optional[CacheEntry]` | Return entry if exists and not expired; else `None`; update `access_count` |
| `set` | `(self, query: str, response: str, model: str, cost: float) -> CacheEntry` | Store new entry; return the entry |
| `invalidate` | `(self, query: str) -> bool` | Remove entry by query; return True if existed |
| `clear` | `(self) -> int` | Remove all entries; return count |
| `stats` | `(self) -> CacheStats` | Return hits, misses, hit_rate, entry_count |
| `_cleanup_expired` | `(self) -> int` | Remove expired entries; return count removed |

#### `CacheStats` (Pydantic BaseModel)

| Field | Type |
|-------|------|
| `hits` | `int` |
| `misses` | `int` |
| `hit_rate` | `float` |
| `entry_count` | `int` |
| `total_cost_saved` | `float` |

### 4.4 Internal State

- `_store: Dict[str, CacheEntry]` -- keyed by MD5 hex digest.
- `_hits: int`, `_misses: int` -- running counters.

### 4.5 Key Design Decision: Query-Focused Keys

```
WRONG:  cache_key = md5(system_prompt + user_query)
           -> system prompt is identical 95% of the time -> wasted entropy
RIGHT:  cache_key = md5(user_query)
           -> higher hit rate, ignores static system prompts
```

### 4.6 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| `get` on expired entry | Delete entry, increment miss count, return `None` |
| `set` with empty query | Raise `ValueError("Query must not be empty")` |
| Hash collision (extremely rare) | Accept overwrite; log warning with both queries |

### 4.7 Production Considerations (Future)

- Replace `Dict` backend with Redis via an adapter interface `CacheBackend(Protocol)`.
- Add LRU eviction when entry count exceeds configurable max.
- Add user-scoped keys: `md5(user_id + query)`.

### 4.8 Testing Requirements

- Unit: 8+ tests covering set/get, TTL expiry, invalidation, stats, empty query rejection.
- Edge: get before any set, get after clear, concurrent-ish access (threading test).
- Performance: 10 000 set+get operations in < 500 ms.

---

## 5. Component 4: Event Tracking

### 5.1 Purpose

Log every inference event with full metadata for cost accounting, quality measurement, and operational observability.  Persist to local JSON lines files (MVP) with a pluggable backend interface for Kafka / Prometheus in later phases.

### 5.2 File

`src/tracking.py` (~350 lines)

### 5.3 Public Classes

#### `InferenceEvent` (Pydantic BaseModel)

| Field | Type | Description |
|-------|------|-------------|
| `request_id` | `str` | UUID-based unique ID |
| `timestamp` | `datetime` | UTC time of event |
| `user_id` | `Optional[str]` | Caller identity (if available) |
| `task_type` | `Optional[str]` | e.g. `summarization`, `faq` |
| `model_selected` | `str` | Model that handled the request |
| `cache_hit` | `bool` | Whether cache was used |
| `input_tokens` | `int` | Actual input token count |
| `output_tokens` | `int` | Actual output token count |
| `total_tokens` | `int` | Sum |
| `latency_ms` | `int` | End-to-end latency |
| `cost` | `float` | Computed dollar cost |
| `routing_reason` | `str` | Why this model was chosen |
| `quality_score` | `Optional[float]` | Predicted or measured quality |

#### `EventTracker`

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, log_dir: Path = Path("data/logs"))` | Ensure log directory exists |
| `log_event` | `(self, event: InferenceEvent) -> None` | Append JSON line to daily log file; store in memory |
| `get_metrics` | `(self) -> Dict[str, Any]` | Aggregate: total_cost, requests, avg_latency, cache_hit_rate, cost_by_model, savings_vs_baseline |
| `get_events` | `(self, since: Optional[datetime] = None, limit: int = 100) -> List[InferenceEvent]` | Query in-memory store |
| `load_from_file` | `(self, path: Path) -> None` | Re-hydrate events from existing JSONL file |
| `export_csv` | `(self, path: Path) -> None` | Export events for analysis |

### 5.4 Log File Format

One JSON object per line (JSONL), file named `data/logs/events_YYYY-MM-DD.jsonl`.

### 5.5 Metrics Calculations

```
total_cost = sum(event.cost for event in events)
avg_latency = mean(event.latency_ms for event in events)
cache_hit_rate = count(event.cache_hit == True) / total_events
savings_vs_baseline = sum(baseline_gpt4_cost - event.cost for event in events)
cost_by_model = group_sum(event.cost, by=event.model_selected)
```

Baseline cost per request: assume GPT-4 Turbo at `(input_tokens * 0.010 + output_tokens * 0.030) / 1000`.

### 5.6 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Log directory does not exist | Create it; log info message |
| File write fails (disk full) | Log error; do NOT crash the inference pipeline |
| Corrupted JSONL line on load | Skip line; log warning with line number |

### 5.7 Testing Requirements

- Unit: 8+ tests covering log, metrics aggregation, CSV export, file load, corrupted line handling.
- Edge: empty events, single event, events across midnight boundary.

---

## 6. Component 5: Inference Optimizer (Core Orchestrator)

### 6.1 Purpose

Central orchestrator.  Owns the complete request lifecycle: cache check, routing, inference execution, cost calculation, event logging, response assembly.

### 6.2 File

`src/optimizer.py` (~550 lines)

### 6.3 Public Classes

#### `InferenceOptimizer`

| Method | Signature | Description |
|--------|-----------|-------------|
| `__init__` | `(self, registry: ModelRegistry, router: Router, cache: Cache, tracker: EventTracker)` | Dependency injection |
| `infer` | `(self, prompt: str, task_id: Optional[str], latency_budget_ms: int, quality_threshold: float, cost_budget: Optional[float], user_id: Optional[str]) -> InferenceResult` | Main entry point |
| `_check_cache` | `(self, prompt: str) -> Optional[CacheEntry]` | Delegate to cache.get |
| `_route` | `(self, constraints: RoutingConstraints) -> RoutingDecision` | Delegate to router |
| `_execute_inference` | `(self, model_name: str, prompt: str) -> Tuple[str, int, int, int]` | Call provider API; return (response, input_tokens, output_tokens, latency_ms) |
| `_calculate_cost` | `(self, model_name: str, input_tokens: int, output_tokens: int) -> float` | `(input_tokens * cost_input / 1000) + (output_tokens * cost_output / 1000)` |
| `_estimate_tokens` | `(self, text: str) -> int` | Rough estimate: `len(text.split()) * 1.3` |

#### `InferenceResult` (Pydantic BaseModel)

| Field | Type | Description |
|-------|------|-------------|
| `response` | `str` | LLM response text |
| `model_used` | `str` | Selected model name |
| `tokens_input` | `int` | Actual input tokens |
| `tokens_output` | `int` | Actual output tokens |
| `cost` | `float` | Dollar cost |
| `latency_ms` | `int` | End-to-end latency |
| `cache_hit` | `bool` | Whether result came from cache |
| `routing_reason` | `str` | Explanation of model choice |
| `request_id` | `str` | UUID for tracing |

### 6.4 Request Flow (step by step)

```
1. Generate request_id (uuid4 short)
2. CACHE CHECK
   entry = cache.get(prompt)
   if entry:
       log event (cache_hit=True, cost=0, model="cache")
       return InferenceResult(response=entry.response, cache_hit=True, cost=0)
3. ESTIMATE TOKENS
   estimated_tokens = _estimate_tokens(prompt)
4. ROUTE
   constraints = RoutingConstraints(quality_threshold, latency_budget_ms, cost_budget)
   decision = router.select_model(constraints)
5. EXECUTE
   start_time = now()
   response_text, actual_input, actual_output, provider_latency = _execute_inference(decision.model_name, prompt)
   total_latency = now() - start_time
6. CALCULATE COST
   cost = _calculate_cost(decision.model_name, actual_input, actual_output)
7. CACHE RESULT
   cache.set(prompt, response_text, decision.model_name, cost)
8. LOG EVENT
   tracker.log_event(InferenceEvent(...))
9. RETURN
   return InferenceResult(...)
```

### 6.5 Provider Adapters

For MVP, two adapters are needed:

| Provider | SDK | Call Pattern |
|----------|-----|-------------|
| OpenAI | `openai` | `client.chat.completions.create(model=..., messages=[...])` |
| Anthropic | `anthropic` | `client.messages.create(model=..., messages=[...])` |

Both adapters must:
- Accept a `model_name` and `prompt` string.
- Return `(response_text: str, input_tokens: int, output_tokens: int, latency_ms: int)`.
- Implement retry with exponential backoff (3 retries, base delay 1s).
- On total failure, raise `ProviderError` so the optimizer can attempt fallback.

### 6.6 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Selected model API down | Retry 3x with backoff; then fall back to next best model from router |
| All providers down | Return HTTP 503 with `retry_after` header; log critical alert |
| Rate limit (429) | Queue request; implement token bucket; return estimated wait time |
| Invalid input (empty prompt, too long) | Return HTTP 400 with descriptive error; log warning |
| Cost calculation fails (model not in registry) | Log error; use estimated cost of $0 and flag in response |

### 6.7 Testing Requirements

- Unit: 10+ tests covering cache hit path, cache miss path, provider fallback, cost calculation, error cases.
- Integration: end-to-end test with mocked provider returning known responses.
- Performance: optimizer overhead (excluding actual LLM call) < 15 ms.

---

## 7. Component 6: REST API

### 7.1 Purpose

HTTP interface exposing the optimizer to external applications.  Validates inputs, formats responses, handles errors with proper status codes.

### 7.2 File

`src/api.py` (~200 lines)

### 7.3 Endpoints

#### `POST /infer`

Request body:
```json
{
  "prompt": "string (required, 1-100000 chars)",
  "task_id": "string (optional)",
  "latency_budget_ms": 300,
  "quality_threshold": 3.5,
  "cost_budget": null
}
```

Response 200:
```json
{
  "response": "...",
  "model_used": "claude-3-5-sonnet",
  "tokens_input": 2150,
  "tokens_output": 45,
  "cost": 0.003,
  "latency_ms": 245,
  "cache_hit": false,
  "routing_reason": "Best quality/cost ratio among 3 candidates",
  "request_id": "req_a1b2c3"
}
```

Response 400:
```json
{
  "error": "validation_error",
  "message": "prompt is required",
  "details": {}
}
```

Response 503:
```json
{
  "error": "service_unavailable",
  "message": "All model providers are currently unavailable",
  "retry_after_seconds": 30
}
```

#### `GET /metrics`

Response 200:
```json
{
  "total_cost": 12.45,
  "total_requests": 342,
  "avg_latency_ms": 145.2,
  "cache_hit_rate": 0.27,
  "cost_by_model": { "gpt-4-turbo": 6.23, "claude-3-5-sonnet": 2.12 },
  "estimated_savings_vs_gpt4": 18.95
}
```

#### `GET /health`

Response 200:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "components": {
    "cache": "healthy",
    "router": "healthy",
    "tracker": "healthy"
  }
}
```

### 7.4 Middleware and Cross-Cutting

- **Request ID**: generate and attach to every request; include in response headers (`X-Request-Id`).
- **Request validation**: use Pydantic models for body parsing; return 400 on failure.
- **CORS**: configurable allowed origins for dashboard integration.
- **Rate limiting**: configurable per-IP limit (default: 100 req/min) for MVP.
- **Structured JSON logging**: every request/response logged with request_id, status, latency.

### 7.5 Error Handling

| HTTP Status | When |
|-------------|------|
| 400 | Missing required field, invalid type, prompt too long |
| 404 | Unknown endpoint |
| 429 | Rate limit exceeded |
| 500 | Unexpected internal error |
| 503 | All providers unavailable |

### 7.6 Testing Requirements

- Unit: 10+ tests using Flask test client covering all endpoints, all error codes.
- Edge: empty body, massive prompt, missing content-type header.

---

## 8. Performance Targets (Phase 1)

| Metric | Target |
|--------|--------|
| Cache lookup | < 1 ms |
| Request analysis | 1-2 ms |
| Router decision | 2-5 ms |
| Event logging | 1-3 ms |
| Total Asahi overhead (excl. LLM call) | 5-11 ms |
| Cost savings vs all-GPT-4 baseline | 58% |

### Cost Example (1000 requests/day)

```
Baseline (GPT-4 for everything):
  1000 req x avg 2000 input + 400 output tokens
  = 1000 x ($0.020 + $0.012) = $32/day

With Asahi (routing + cache):
  350 cache hits = $0
  650 routed (mostly to Sonnet/Opus) = avg $0.008
  = 650 x $0.008 = $5.20/day + $0 = $5.20/day

Savings: $26.80/day = 84% on this mix
Conservative estimate across all workloads: 58%
```

---

## 9. Monitoring and Alerting (MVP)

| Alert | Trigger | Action |
|-------|---------|--------|
| Cache hit rate low | < 10% over 1 hour | Check cache configuration; may indicate all-unique queries |
| API latency spike | p95 > 2x rolling average | Investigate provider or network issues |
| Error rate high | > 1% of requests | Check provider status pages |
| Cost spike | Daily cost > 2x 7-day rolling average | Alert ops team; review traffic patterns |
| Token estimation drift | Actual tokens > 1.2x estimated | Tune estimation multiplier |

---

## 10. Deployment (MVP)

```
Development Machine
  └── Asahi Application
      ├── Python 3.10+
      ├── Flask API server (port 5000)
      ├── In-memory cache (Python dict)
      ├── Local JSON logs (data/logs/)
      └── .env file (API keys)
```

Run: `python -m src.api` or `flask run --port 5000`

---

## 11. Dependencies (Phase 1)

| Package | Version | Purpose |
|---------|---------|---------|
| flask | >= 2.3 | REST API |
| pydantic | >= 2.0 | Data validation and models |
| anthropic | >= 0.25 | Claude API |
| openai | >= 1.0 | GPT API |
| pyyaml | >= 6.0 | Config loading |
| python-dotenv | >= 1.0 | Env file loading |
| pytest | >= 7.0 | Testing |
| pytest-cov | >= 4.0 | Coverage |
| black | latest | Formatting |
| flake8 | latest | Linting |
| mypy | latest | Type checking |

---

## 12. Acceptance Criteria

Every item must pass before Phase 1 is considered complete:

- [ ] 28/28 unit tests passing
- [ ] `mypy --strict src/` reports zero errors
- [ ] `black --check src/` reports no changes needed
- [ ] `flake8 src/ --max-line-length=100` reports zero warnings
- [ ] `pytest --cov=src --cov-fail-under=90` passes
- [ ] Every public function has a docstring
- [ ] Zero hardcoded model names, thresholds, or API keys in source code
- [ ] `/health` endpoint returns healthy status
- [ ] `/infer` returns correct response for a test prompt (mocked provider)
- [ ] `/metrics` returns accurate aggregates after 10 test requests
- [ ] Cost calculation matches manual verification within 0.1%
- [ ] Cache hit on repeated prompt returns identical response with cost $0
