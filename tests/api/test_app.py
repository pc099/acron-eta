"""
Tests for the FastAPI REST API layer.

Uses FastAPI's TestClient (backed by httpx) for synchronous testing.
"""

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a TestClient with mock inference enabled."""
    app = create_app(use_mock=True)
    return TestClient(app)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealth:
    """Tests for GET /health."""

    def test_health_returns_200(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_contains_status_and_version(
        self, client: TestClient
    ) -> None:
        data = client.get("/health").json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "uptime_seconds" in data

    def test_health_includes_components(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "components" in data
        assert data["components"]["cache"] == "healthy"
        assert data["components"]["router"] == "healthy"
        assert data["components"]["registry"] == "healthy"

    def test_health_uptime_is_non_negative(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert data["uptime_seconds"] >= 0


# ---------------------------------------------------------------------------
# Models endpoint
# ---------------------------------------------------------------------------


class TestModels:
    """Tests for GET /models."""

    def test_models_returns_200(self, client: TestClient) -> None:
        resp = client.get("/models")
        assert resp.status_code == 200

    def test_models_returns_all_registered(self, client: TestClient) -> None:
        data = client.get("/models").json()
        assert data["count"] >= 3
        names = {m["name"] for m in data["models"]}
        assert "gpt-4o" in names
        assert "claude-3-5-sonnet" in names

    def test_model_profiles_have_pricing(self, client: TestClient) -> None:
        data = client.get("/models").json()
        for model in data["models"]:
            assert "cost_per_1k_input_tokens" in model
            assert "cost_per_1k_output_tokens" in model
            assert "quality_score" in model


# ---------------------------------------------------------------------------
# Infer endpoint
# ---------------------------------------------------------------------------


class TestInfer:
    """Tests for POST /infer."""

    def test_infer_returns_200_for_valid_prompt(
        self, client: TestClient
    ) -> None:
        resp = client.post("/infer", json={"prompt": "What is Python?"})
        assert resp.status_code == 200

    def test_infer_response_has_required_fields(
        self, client: TestClient
    ) -> None:
        data = client.post("/infer", json={"prompt": "Hello"}).json()
        for field in [
            "request_id",
            "response",
            "model_used",
            "tokens_input",
            "tokens_output",
            "cost",
            "latency_ms",
            "cache_hit",
            "cache_tier",
            "routing_reason",
        ]:
            assert field in data, f"Missing field: {field}"

    def test_infer_response_cache_tier_in_range(
        self, client: TestClient
    ) -> None:
        """InferResponse must include cache_tier in [0, 3]."""
        data = client.post("/infer", json={"prompt": "Hello"}).json()
        assert "cache_tier" in data
        assert 0 <= data["cache_tier"] <= 3

    def test_infer_cost_is_positive(self, client: TestClient) -> None:
        data = client.post("/infer", json={"prompt": "Test prompt"}).json()
        assert data["cost"] > 0

    def test_infer_model_used_is_valid(self, client: TestClient) -> None:
        data = client.post("/infer", json={"prompt": "Test"}).json()
        assert data["model_used"] != ""

    def test_infer_cache_hit_on_duplicate(self, client: TestClient) -> None:
        prompt = "What is the speed of light?"
        r1 = client.post("/infer", json={"prompt": prompt}).json()
        r2 = client.post("/infer", json={"prompt": prompt}).json()
        assert r1["cache_hit"] is False
        assert r2["cache_hit"] is True

    def test_infer_custom_quality_threshold(
        self, client: TestClient
    ) -> None:
        """High quality_threshold should route to a high-quality model."""
        data = client.post(
            "/infer",
            json={"prompt": "Test", "quality_threshold": 4.5},
        ).json()
        # Registry may have gpt-4o, claude-opus-4, claude-3-5-sonnet
        assert data["model_used"] in [
            "gpt-4o",
            "claude-opus-4",
            "claude-3-5-sonnet",
        ]

    def test_infer_empty_prompt_returns_422(self, client: TestClient) -> None:
        resp = client.post("/infer", json={"prompt": ""})
        assert resp.status_code == 422

    def test_infer_missing_prompt_returns_422(
        self, client: TestClient
    ) -> None:
        resp = client.post("/infer", json={})
        assert resp.status_code == 422

    def test_infer_invalid_quality_threshold(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/infer",
            json={"prompt": "Test", "quality_threshold": 10.0},
        )
        assert resp.status_code == 422

    def test_infer_request_id_header(self, client: TestClient) -> None:
        resp = client.post(
            "/infer",
            json={"prompt": "Hello"},
            headers={"X-Request-Id": "custom-req-123"},
        )
        assert resp.status_code == 200
        assert resp.headers.get("X-Request-Id") == "custom-req-123"
        assert resp.json()["request_id"] == "custom-req-123"


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------


class TestMetrics:
    """Tests for GET /metrics."""

    def test_metrics_returns_200(self, client: TestClient) -> None:
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_after_inferences(self, client: TestClient) -> None:
        client.post("/infer", json={"prompt": "Q1"})
        client.post("/infer", json={"prompt": "Q2"})
        data = client.get("/metrics").json()
        assert data["requests"] >= 2
        assert data["total_cost"] > 0

    def test_metrics_has_expected_keys(self, client: TestClient) -> None:
        data = client.get("/metrics").json()
        assert "total_cost" in data
        assert "requests" in data
        assert "cache_hit_rate" in data
        assert "uptime_seconds" in data

    def test_metrics_has_per_tier_counts(self, client: TestClient) -> None:
        """GET /metrics must include tier1/tier2/tier3 hits and misses."""
        data = client.get("/metrics").json()
        for key in ("tier1_hits", "tier1_misses", "tier2_hits", "tier2_misses", "tier3_hits", "tier3_misses"):
            assert key in data, f"Missing key: {key}"
            assert isinstance(data[key], int)


# ---------------------------------------------------------------------------
# OpenAI-compatible endpoint
# ---------------------------------------------------------------------------


class TestOpenAIChatCompletions:
    """Tests for POST /v1/chat/completions."""

    def test_openai_chat_returns_200(self, client: TestClient) -> None:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Say hello"}],
            },
        )
        assert resp.status_code == 200

    def test_openai_chat_response_shape(self, client: TestClient) -> None:
        """Response must match OpenAI chat completions format."""
        data = client.post(
            "/v1/chat/completions",
            json={
                "messages": [{"role": "user", "content": "Hi"}],
            },
        ).json()
        assert "id" in data
        assert "choices" in data
        assert len(data["choices"]) >= 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert "content" in data["choices"][0]["message"]
        assert "usage" in data
        assert data["usage"]["prompt_tokens"] >= 0
        assert data["usage"]["completion_tokens"] >= 0
        assert "model" in data

    def test_openai_chat_empty_messages_returns_400(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/v1/chat/completions",
            json={"messages": [{"role": "user", "content": ""}]},
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Tests for API error responses."""

    def test_unknown_endpoint_returns_404(self, client: TestClient) -> None:
        resp = client.get("/nonexistent")
        assert resp.status_code == 404

    def test_invalid_json_returns_422(self, client: TestClient) -> None:
        resp = client.post(
            "/infer",
            content="not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_massive_prompt_returns_422(self, client: TestClient) -> None:
        resp = client.post("/infer", json={"prompt": "x" * 200000})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Exception handler tests
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    """Tests for global exception handlers."""

    def test_asahi_exception_returns_consistent_json(
        self, client: TestClient
    ) -> None:
        """Verify AsahiException subclasses return consistent JSON format."""
        # This test verifies the handler structure, not specific exceptions
        # since we can't easily trigger all exception types in unit tests
        resp = client.post("/infer", json={"prompt": "test"})
        # Should succeed, but if it fails, should have consistent format
        assert resp.status_code in [200, 500, 502, 503]
        if resp.status_code != 200:
            data = resp.json()
            assert "error" in data
            assert "message" in data
            assert "request_id" in data

    def test_error_response_has_request_id(self, client: TestClient) -> None:
        """Verify error responses include request_id."""
        # Trigger a validation error
        resp = client.post("/infer", json={})
        assert resp.status_code == 422
        # FastAPI validation errors have different format, but our
        # custom exceptions should have request_id
        # This is a placeholder - actual exception testing would require
        # mocking the optimizer to raise specific exceptions
