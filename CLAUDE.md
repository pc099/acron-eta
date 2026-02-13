# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Asahi is an LLM inference cost optimization platform. It routes requests to the cheapest model meeting quality/latency constraints, caches at multiple tiers, and provides analytics, governance, and multi-tenancy. Built as a production SaaS backend.

**Stack:** Python 3.12, FastAPI, Pydantic v2, pytest. Windows dev environment (bash via Git Bash/WSL).

## Commands

```bash
# Run all tests (700+ tests, ~70s)
pytest tests/ -v

# Run tests for a single module
pytest tests/cache/test_exact.py -v

# Run tests for a domain
pytest tests/governance/ -v

# Run with coverage
pytest tests/ --cov=src --cov-fail-under=90

# Start API server (mock mode, no API keys needed)
python main.py api --mock

# Start API server (real providers)
python main.py api

# Run benchmark (mock)
python main.py benchmark --mock --num_queries 50

# Single inference
python main.py infer --prompt "What is Python?" --mock

# Lint
black --check src/ tests/
ruff check src/
```

## Architecture

### Request Flow

```
POST /infer → AuthMiddleware → RateLimiter → InferenceOptimizer.infer()
    → Cache.get() [Tier 1 exact match]
    → Router.select_model() [cheapest meeting constraints]
    → _call_openai() or _call_anthropic() [or mock]
    → Cache.set() + EventTracker.log_event()
    → InferenceResult
```

### Key Modules

- **`src/core/optimizer.py`** - `InferenceOptimizer`: central orchestrator. Owns the request lifecycle: cache check, routing, inference, cost calc, event logging. All components are injected via constructor.
- **`src/config.py`** - `Settings` singleton via `get_settings()`. Loads `config/config.yaml`, `.env`, and `ASAHI_*` env overrides. Uses Python dataclasses (not Pydantic) to avoid circular imports. Call `reset_settings()` in tests.
- **`src/api/app.py`** - `create_app()` factory. All shared state lives on `app.state`. Includes middleware for rate limiting, request-ID injection, and API key auth.
- **`config/models.yaml`** - Model profiles loaded by `ModelRegistry`. Defines pricing, latency, quality for each LLM (gpt-4-turbo, claude-opus-4, claude-3-5-sonnet).
- **`config/config.yaml`** - All app settings. Override any value with `ASAHI_<SECTION>_<KEY>` env var (e.g., `ASAHI_API_PORT=9000`).

### Domain Modules

| Domain | Key Classes | Phase |
|--------|------------|-------|
| `src/cache/` | `Cache` (exact), `SemanticCache`, `IntermediateCache` | 1-2 |
| `src/routing/` | `Router`, `TaskTypeDetector`, `RoutingConstraints` | 1-2 |
| `src/embeddings/` | `EmbeddingEngine`, `SimilarityCalculator`, `VectorDatabase` | 2 |
| `src/batching/` | `BatchEngine`, `RequestQueue`, `BatchScheduler` | 3 |
| `src/optimization/` | `TokenOptimizer`, `PromptCompressor`, `FewShotSelector` | 4 |
| `src/features/` | `FeatureStoreClient`, `FeatureEnricher`, `FeatureMonitor` | 5 |
| `src/observability/` | `MetricsCollector`, `AnalyticsEngine`, `AnomalyDetector`, `ForecastingModel` | 6 |
| `src/governance/` | `AuthMiddleware`, `GovernanceEngine`, `AuditLogger`, `ComplianceManager`, `EncryptionManager`, `MultiTenancyManager` | 7 |

### Configuration Pattern

Modules accept optional config via constructor. When `None`, defaults come from central settings:

```python
class Cache:
    def __init__(self, ttl_seconds: Optional[int] = None) -> None:
        _s = get_settings()
        self._ttl_seconds = ttl_seconds if ttl_seconds is not None else _s.cache.ttl_seconds
```

This preserves backward compat -- tests can still do `Cache(ttl_seconds=60)`.

### Test Structure

Tests mirror `src/` structure. Each domain has its own test directory. Tests use pytest fixtures; external APIs are always mocked. All state is in-memory (no DB/Redis/Docker needed for tests).

## Code Standards (from .cursor/rules)

- Type hints on every function, parameter, and return value
- Google-style docstrings on public classes and functions
- No hardcoded values -- use config classes with defaults
- Structured logging with `logging.getLogger(__name__)` and `extra={}` context
- Custom exceptions from `src/exceptions.py` (`AsahiException` hierarchy)
- Config classes suffixed with `Config`, result classes with `Result` or descriptive name
- Private attributes/methods prefixed with `_`

## Current State

- Phases 1-7 complete (cache, routing, embeddings, batching, optimization, features, observability, governance)
- 702 tests passing
- All state in-memory (no persistence layer yet)
- LLM calls are synchronous (blocking the event loop)
- No Docker, CI/CD, or cloud deployment yet
- Frontend wireframes in `docs/ASAHI_FRONTEND_WIREFRAMES.md` and design system in `docs/ASAHI_FRONTEND_DESIGN_SYSTEM.md`
- Production roadmap at `docs/PRODUCTION_ROADMAP.md` (Steps A-K)

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/infer` | Run inference with smart routing |
| GET | `/metrics` | Aggregated cost/latency analytics |
| GET | `/models` | Model registry with pricing |
| GET | `/health` | Health check with component status |
| GET | `/analytics/cost-breakdown` | Cost by model/task/period |
| GET | `/analytics/trends` | Time-series trends |
| GET | `/analytics/forecast` | Cost forecasting |
| GET | `/analytics/anomalies` | Active anomaly alerts |
| GET | `/analytics/recommendations` | Optimization suggestions |
| GET | `/analytics/cache-performance` | Per-tier cache stats |
| GET | `/analytics/latency-percentiles` | p50/p75/p90/p95/p99 |
| GET | `/analytics/prometheus` | Prometheus metrics export |
| POST | `/governance/api-keys` | Generate API key |
| GET | `/governance/audit` | Query audit log |
| GET | `/governance/compliance/report` | Compliance report |
| GET/POST | `/governance/policies/{org_id}` | Policy CRUD |
