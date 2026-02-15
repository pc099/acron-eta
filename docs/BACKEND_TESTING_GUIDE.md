# Backend Server Testing Guide

This guide covers **automated** testing of the Asahi backend: running the test suite, test layout, coverage, and how to add or debug tests. For manual testing of the running API (curl, scripts, CLI), see [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Running Tests](#2-running-tests)
3. [Test Layout](#3-test-layout)
4. [Test Conventions](#4-test-conventions)
5. [API (FastAPI) Tests](#5-api-fastapi-tests)
6. [Unit Tests by Domain](#6-unit-tests-by-domain)
7. [Coverage](#7-coverage)
8. [Writing New Tests](#8-writing-new-tests)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Prerequisites

- **Python 3.10+** (3.12 recommended)
- Dependencies from `requirements.txt` (includes `pytest`, `pytest-cov`, `pytest-asyncio`, `fakeredis`)

```bash
cd d:\claude\asahi
pip install -r requirements.txt
```

No API keys are required for the test suite: tests use **mock inference** (`use_mock=True`) and **fakeredis** where Redis is needed, so the suite runs offline and without credentials.

---

## 2. Running Tests

### Run all tests

```bash
# From project root
pytest

# Verbose
pytest -v

# With short tracebacks
pytest -v --tb=short
```

Default config (from `pytest.ini`):

- `testpaths = tests`
- `addopts = -v --tb=short`
- `asyncio_mode = auto` for async tests

### Run by directory (domain)

```bash
# API only
pytest tests/api/ -v

# Core optimizer only
pytest tests/core/ -v

# Cache (exact, semantic, redis, intermediate, workflow)
pytest tests/cache/ -v

# Routing (router, advanced, constraints, task_detector)
pytest tests/routing/ -v

# Embeddings
pytest tests/embeddings/ -v

# Config
pytest tests/test_config.py -v

# Governance (auth, audit, compliance, encryption, rbac, tenancy)
pytest tests/governance/ -v

# Observability, features, batching, optimization, tracking, models
pytest tests/observability/ -v
pytest tests/features/ -v
pytest tests/batching/ -v
pytest tests/optimization/ -v
pytest tests/tracking/ -v
pytest tests/models/ -v
```

### Run by file or test name

```bash
# Single file
pytest tests/api/test_app.py -v

# Single class
pytest tests/api/test_app.py::TestHealth -v

# Single test
pytest tests/api/test_app.py::TestHealth::test_health_returns_200 -v

# By keyword
pytest -v -k "infer and not empty"
```

### Acceptance tests

```bash
pytest tests/test_acceptance.py -v
```

These assert Phase 1 acceptance criteria end-to-end (health, infer, metrics).

---

## 3. Test Layout

Tests mirror `src/` by **domain** (not by phase):

| Source folder     | Test folder        | Notes                          |
|------------------|--------------------|---------------------------------|
| `src/api/`       | `tests/api/`       | FastAPI app, routes, middleware |
| `src/core/`      | `tests/core/`      | InferenceOptimizer              |
| `src/cache/`     | `tests/cache/`     | Exact, Redis, semantic, intermediate, workflow |
| `src/routing/`   | `tests/routing/`  | Router, advanced, constraints, task_detector |
| `src/embeddings/`| `tests/embeddings/`| Engine, similarity, threshold, vector_store, etc. |
| `src/models/`    | `tests/models/`   | Registry, providers            |
| `src/tracking/`  | `tests/tracking/`| EventTracker                   |
| `src/config`      | `tests/test_config.py` | Settings, YAML, env overrides |
| …                | `tests/<domain>/` | Same pattern for batching, optimization, features, observability, governance |

Root-level scripts like `test_phase2.py` and `test_similarity_detailed.py` are **manual/exploratory** scripts (optional); the canonical automated suite lives under `tests/`.

---

## 4. Test Conventions

- **Framework:** pytest (no unittest).
- **Naming:** `test_<method>_<scenario>` or `test_<behavior>`; classes group related tests (e.g. `TestHealth`, `TestInfer`).
- **Type hints:** Use on test functions and fixtures (e.g. `def test_foo(client: TestClient) -> None`).
- **Fixtures:** Prefer shared fixtures (e.g. `client`, `optimizer`) in the test module or a future `conftest.py`; use `autouse` only when needed (e.g. resetting config).
- **Isolation:** No real APIs or real Redis in unit tests: use `use_mock=True` for inference and `fakeredis` for Redis-backed code.
- **Docstrings:** Short class/module docstrings are encouraged; test names should be self-explanatory.

---

## 5. API (FastAPI) Tests

API tests use FastAPI’s **TestClient** (httpx). The app is created with **mock inference** so no LLM calls are made.

### Fixture pattern

```python
from fastapi.testclient import TestClient
from src.api.app import create_app

@pytest.fixture
def client() -> TestClient:
    app = create_app(use_mock=True)
    return TestClient(app)
```

### Example: health and infer

```python
def test_health_returns_200(self, client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200

def test_infer_returns_200_for_valid_prompt(self, client: TestClient) -> None:
    resp = client.post("/infer", json={"prompt": "What is Python?"})
    assert resp.status_code == 200
    data = resp.json()
    assert "response" in data
    assert "model_used" in data
    assert data["cost"] > 0
```

### Validation (422) and headers

```python
def test_infer_empty_prompt_returns_422(self, client: TestClient) -> None:
    resp = client.post("/infer", json={"prompt": ""})
    assert resp.status_code == 422

def test_infer_request_id_header(self, client: TestClient) -> None:
    resp = client.post(
        "/infer",
        json={"prompt": "Hello"},
        headers={"X-Request-Id": "custom-req-123"},
    )
    assert resp.status_code == 200
    assert resp.headers.get("X-Request-Id") == "custom-req-123"
```

Run API tests:

```bash
pytest tests/api/test_app.py -v
```

---

## 6. Unit Tests by Domain

### Core (optimizer)

- **File:** `tests/core/test_optimizer.py`
- **Fixture:** `optimizer` = `InferenceOptimizer(use_mock=True)`
- **Covers:** infer result shape, cache hits, force model, routing, metrics, baseline vs optimized.

```bash
pytest tests/core/test_optimizer.py -v
```

### Config

- **File:** `tests/test_config.py`
- **Covers:** YAML loading, env overrides, `Settings`, `get_settings`, `reset_settings` (uses `autouse` fixture to reset singleton).

```bash
pytest tests/test_config.py -v
```

### Cache, routing, embeddings, etc.

Same idea: one test file per main module under `tests/<domain>/`, using mocks/fakeredis and no real external services.

---

## 7. Coverage

### Generate coverage report

```bash
# Coverage for entire src tree
pytest --cov=src --cov-report=term-missing

# HTML report (open htmlcov/index.html)
pytest --cov=src --cov-report=html

# Fail if coverage below 80% (adjust as needed)
pytest --cov=src --cov-fail-under=80
```

### By domain

```bash
pytest tests/api/       --cov=src.api       --cov-report=term-missing
pytest tests/core/      --cov=src.core      --cov-report=term-missing
pytest tests/cache/     --cov=src.cache     --cov-report=term-missing
pytest tests/routing/   --cov=src.routing   --cov-report=term-missing
```

Project standards (see [QUALITY_STANDARDS.md](QUALITY_STANDARDS.md)) may require high coverage per component; use the domain-level commands above to check before merging.

---

## 8. Writing New Tests

### Adding an API test

1. Open `tests/api/test_app.py` (or add a new file under `tests/api/` if you prefer).
2. Use the existing `client` fixture (or define one that calls `create_app(use_mock=True)` and `TestClient(app)`).
3. Add a method to the right class (e.g. `TestInfer`) or add a new class:

```python
def test_infer_new_behavior(self, client: TestClient) -> None:
    resp = client.post("/infer", json={"prompt": "New scenario", "quality_threshold": 4.0})
    assert resp.status_code == 200
    # assert on response body
```

### Adding a unit test for a domain module

1. Find the right file: `src/<domain>/<module>.py` → `tests/<domain>/test_<module>.py`.
2. If the module talks to Redis, use a fakeredis fixture (see existing cache tests).
3. If the code calls LLM/inference, inject a mock or use an optimizer with `use_mock=True`.

Example skeleton:

```python
# tests/example/test_my_module.py
import pytest
from src.example.my_module import MyClass, MyConfig

@pytest.fixture
def config() -> MyConfig:
    return MyConfig(threshold=0.9)

@pytest.fixture
def service(config: MyConfig) -> MyClass:
    return MyClass(config)

def test_behavior(service: MyClass) -> None:
    result = service.do_something("input")
    assert result.value == "expected"
```

### Async tests

If you add async route handlers or async code, use `pytest-asyncio` (already configured in `pytest.ini` with `asyncio_mode = auto`). Mark async tests with `@pytest.mark.asyncio` if needed, or rely on `auto` for `async def test_*` functions.

---

## 9. Troubleshooting

### Tests fail with "Application not initialised" / app.state

- API tests must use an app instance created in the test process. Use `create_app(use_mock=True)` and pass it to `TestClient(app)`; do not rely on a global app or a different process.

### Redis connection errors in tests

- Use **fakeredis** so tests don’t need a real Redis. See `tests/cache/test_redis_backend.py` (or similar) for a fixture pattern.

### Import errors (e.g. `src.api.app` or `src.core.optimizer`)

- Run pytest from the **project root** (`d:\claude\asahi`) so `src` is on `PYTHONPATH`. If you use an IDE, set the project root as the working directory for the test runner.

### Slow tests

- Most slowness comes from real I/O. Ensure mocks are used for inference and fakeredis for Redis; run a subset during development, e.g. `pytest tests/api/ tests/core/ -v`.

### 422 on valid-looking request

- Check request body against Pydantic models in `src/api/app.py` (or schemas): field names, types, and constraints (e.g. `min_length=1` for `prompt`). Read the response body for validation error details.

### Coverage too low

- Run `pytest --cov=src --cov-report=term-missing` and add tests for uncovered lines or branches in the target module. Focus on public behavior and error paths.

---

## Quick reference

| Goal                    | Command |
|-------------------------|--------|
| All tests               | `pytest` or `pytest -v` |
| API tests only          | `pytest tests/api/ -v` |
| Core optimizer only     | `pytest tests/core/ -v` |
| One test                | `pytest tests/api/test_app.py::TestHealth::test_health_returns_200 -v` |
| Coverage (terminal)     | `pytest --cov=src --cov-report=term-missing` |
| Coverage (HTML)         | `pytest --cov=src --cov-report=html` |
| Acceptance criteria     | `pytest tests/test_acceptance.py -v` |

For manual testing of the running server (curl, scripts, env vars), see [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md).
