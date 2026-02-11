"""
Phase 1 acceptance criteria verification.

This test module validates every acceptance criterion from the
phase1_requirements.md specification.
"""

from fastapi.testclient import TestClient

from src.api import create_app


class TestAcceptanceCriteria:
    """Verify Phase 1 acceptance criteria end-to-end."""

    def test_health_endpoint_returns_healthy(self) -> None:
        app = create_app(use_mock=True)
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_infer_returns_correct_response(self) -> None:
        app = create_app(use_mock=True)
        client = TestClient(app)
        resp = client.post("/infer", json={"prompt": "What is Python?"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["response"] != ""
        assert data["model_used"] != ""
        assert data["cost"] > 0

    def test_metrics_accurate_after_10_requests(self) -> None:
        app = create_app(use_mock=True)
        client = TestClient(app)
        prompts = [
            "What is Python?",
            "Explain gravity.",
            "What is 2+2?",
            "Write a poem.",
            "Translate hello.",
            "What is DNA?",
            "Summarize AI.",
            "Classify: great!",
            "What is TCP?",
            "Debug: print(1",
        ]
        for p in prompts:
            client.post("/infer", json={"prompt": p})
        data = client.get("/metrics").json()
        assert data["requests"] == 10
        assert data["total_cost"] > 0

    def test_cache_hit_returns_zero_cost(self) -> None:
        app = create_app(use_mock=True)
        client = TestClient(app)
        prompt = "Repeated query for cache test"
        r1 = client.post("/infer", json={"prompt": prompt}).json()
        r2 = client.post("/infer", json={"prompt": prompt}).json()
        assert r1["cache_hit"] is False
        assert r1["cost"] > 0
        assert r2["cache_hit"] is True
        assert r2["cost"] == 0.0
        assert r2["response"] == r1["response"]

    def test_no_hardcoded_api_keys_in_source(self) -> None:
        import re
        from pathlib import Path

        src_dir = Path("src")
        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text()
            # Check for hardcoded API keys
            assert not re.search(
                r"sk-[a-zA-Z0-9]{20,}", content
            ), f"Hardcoded API key found in {py_file}"
