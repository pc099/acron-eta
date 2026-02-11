"""Tests for IntermediateCache (Tier 3 orchestrator)."""

import time

import pytest

from src.cache.intermediate import IntermediateCache
from src.cache.workflow import WorkflowStep


@pytest.fixture
def cache() -> IntermediateCache:
    return IntermediateCache(ttl_seconds=3600)


def make_step(
    step_id: str, cache_key: str, step_type: str = "answer"
) -> WorkflowStep:
    """Helper to create a WorkflowStep."""
    return WorkflowStep(
        step_id=step_id,
        step_type=step_type,
        intent="test intent",
        input_text="test input",
        cache_key=cache_key,
    )


class TestGetSet:
    """Tests for get and set."""

    def test_get_miss(self, cache: IntermediateCache) -> None:
        result = cache.get("nonexistent")
        assert result is None

    def test_set_and_get(self, cache: IntermediateCache) -> None:
        cache.set("key1", "result1")
        result = cache.get("key1")
        assert result == "result1"

    def test_ttl_expiry(self) -> None:
        cache = IntermediateCache(ttl_seconds=1)
        cache.set("key1", "result1")
        time.sleep(1.1)
        result = cache.get("key1")
        assert result is None


class TestInvalidate:
    """Tests for invalidate."""

    def test_invalidate_existing(self, cache: IntermediateCache) -> None:
        cache.set("key1", "result1")
        assert cache.invalidate("key1") is True
        assert cache.get("key1") is None

    def test_invalidate_nonexistent(self, cache: IntermediateCache) -> None:
        assert cache.invalidate("nonexistent") is False


class TestInvalidateByDocument:
    """Tests for invalidate_by_document."""

    def test_invalidate_by_document(self, cache: IntermediateCache) -> None:
        cache.set("doc1:summarize:abc", "summary1")
        cache.set("doc1:answer:def", "answer1")
        cache.set("doc2:summarize:ghi", "summary2")
        count = cache.invalidate_by_document("doc1")
        assert count == 2
        assert cache.get("doc1:summarize:abc") is None
        assert cache.get("doc2:summarize:ghi") == "summary2"

    def test_invalidate_by_document_none(self, cache: IntermediateCache) -> None:
        count = cache.invalidate_by_document("nonexistent")
        assert count == 0


class TestExecuteWorkflow:
    """Tests for execute_workflow."""

    def test_all_misses(self, cache: IntermediateCache) -> None:
        steps = [
            make_step("s1", "key1"),
            make_step("s2", "key2"),
        ]
        executor = lambda step: f"executed_{step.step_id}"
        result = cache.execute_workflow(steps, executor)
        assert result[0].result == "executed_s1"
        assert result[1].result == "executed_s2"

    def test_all_hits(self, cache: IntermediateCache) -> None:
        cache.set("key1", "cached_s1")
        cache.set("key2", "cached_s2")
        steps = [
            make_step("s1", "key1"),
            make_step("s2", "key2"),
        ]
        call_count = 0

        def executor(step: WorkflowStep) -> str:
            nonlocal call_count
            call_count += 1
            return f"executed_{step.step_id}"

        result = cache.execute_workflow(steps, executor)
        assert result[0].result == "cached_s1"
        assert result[1].result == "cached_s2"
        assert call_count == 0  # No executions needed

    def test_mixed_hits_misses(self, cache: IntermediateCache) -> None:
        cache.set("key1", "cached_s1")
        steps = [
            make_step("s1", "key1"),  # hit
            make_step("s2", "key2"),  # miss
        ]
        executor = lambda step: f"executed_{step.step_id}"
        result = cache.execute_workflow(steps, executor)
        assert result[0].result == "cached_s1"
        assert result[1].result == "executed_s2"

    def test_workflow_caches_misses(self, cache: IntermediateCache) -> None:
        steps = [make_step("s1", "key1")]
        executor = lambda step: "new_result"
        cache.execute_workflow(steps, executor)
        # Should now be cached
        assert cache.get("key1") == "new_result"


class TestStats:
    """Tests for stats."""

    def test_stats_empty(self, cache: IntermediateCache) -> None:
        stats = cache.stats()
        assert stats["tier"] == 3
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["entry_count"] == 0

    def test_stats_after_operations(self, cache: IntermediateCache) -> None:
        cache.set("key1", "result1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["entry_count"] == 1
