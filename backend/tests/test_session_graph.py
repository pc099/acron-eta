"""Tests for the session graph store service."""

import time
from unittest.mock import patch

import pytest

from app.services.session_graph import SessionGraphStore, StepNode


@pytest.fixture
def store() -> SessionGraphStore:
    return SessionGraphStore()


class TestSessionGraphStore:
    """Tests for SessionGraphStore."""

    def test_add_step(self, store: SessionGraphStore) -> None:
        node = store.add_step("session-1", step_number=1, call_trace_id="trace-1")
        assert node.step_number == 1
        assert node.call_trace_id == "trace-1"
        assert node.depends_on == []

    def test_add_step_with_dependencies(self, store: SessionGraphStore) -> None:
        store.add_step("session-1", step_number=1, call_trace_id="trace-1")
        node = store.add_step(
            "session-1", step_number=2,
            call_trace_id="trace-2", depends_on=[1],
        )
        assert node.depends_on == [1]

    def test_get_step(self, store: SessionGraphStore) -> None:
        store.add_step("session-1", step_number=1, call_trace_id="trace-1")
        node = store.get_step("session-1", 1)
        assert node is not None
        assert node.call_trace_id == "trace-1"

    def test_get_step_not_found(self, store: SessionGraphStore) -> None:
        assert store.get_step("nonexistent", 1) is None

    def test_get_dependencies_transitive(self, store: SessionGraphStore) -> None:
        store.add_step("session-1", step_number=1)
        store.add_step("session-1", step_number=2, depends_on=[1])
        store.add_step("session-1", step_number=3, depends_on=[2])

        deps = store.get_dependencies("session-1", 3)
        dep_steps = {d.step_number for d in deps}
        assert dep_steps == {1, 2}

    def test_get_dependencies_empty(self, store: SessionGraphStore) -> None:
        store.add_step("session-1", step_number=1)
        deps = store.get_dependencies("session-1", 1)
        assert deps == []

    def test_get_session_graph(self, store: SessionGraphStore) -> None:
        store.add_step("session-1", step_number=1)
        store.add_step("session-1", step_number=2)
        graph = store.get_session_graph("session-1")
        assert graph is not None
        assert graph.step_count == 2
        assert graph.latest_step == 2

    def test_get_session_graph_not_found(self, store: SessionGraphStore) -> None:
        assert store.get_session_graph("nonexistent") is None

    def test_remove_session(self, store: SessionGraphStore) -> None:
        store.add_step("session-1", step_number=1)
        assert store.remove_session("session-1") is True
        assert store.get_session_graph("session-1") is None

    def test_remove_session_not_found(self, store: SessionGraphStore) -> None:
        assert store.remove_session("nonexistent") is False

    def test_invalid_step_number(self, store: SessionGraphStore) -> None:
        with pytest.raises(ValueError, match="positive"):
            store.add_step("session-1", step_number=0)

    def test_step_with_metadata(self, store: SessionGraphStore) -> None:
        node = store.add_step(
            "session-1", step_number=1,
            metadata={"tool": "search"},
        )
        assert node.metadata == {"tool": "search"}

    def test_multiple_sessions_isolated(self, store: SessionGraphStore) -> None:
        store.add_step("session-1", step_number=1)
        store.add_step("session-2", step_number=1)
        assert store.get_session_graph("session-1").step_count == 1
        assert store.get_session_graph("session-2").step_count == 1


class TestSessionGraphTTL:
    """Tests for TTL management."""

    def test_custom_ttl(self) -> None:
        store = SessionGraphStore(ttl_seconds=60)
        assert store._ttl_seconds == 60

    def test_expired_session_returns_none(self) -> None:
        store = SessionGraphStore(ttl_seconds=1)
        store.add_step("s1", step_number=1)
        # Simulate time passing
        store._graphs["s1"].last_accessed_at = time.time() - 10
        assert store.get_step("s1", 1) is None
        # Graph should be cleaned up
        assert "s1" not in store._graphs

    def test_access_refreshes_ttl(self) -> None:
        store = SessionGraphStore(ttl_seconds=100)
        store.add_step("s1", step_number=1)
        before = store._graphs["s1"].last_accessed_at
        time.sleep(0.01)
        store.get_step("s1", 1)
        after = store._graphs["s1"].last_accessed_at
        assert after > before

    def test_cleanup_expired_removes_old(self) -> None:
        store = SessionGraphStore(ttl_seconds=1)
        store.add_step("s1", step_number=1)
        store.add_step("s2", step_number=1)
        # Expire s1 only
        store._graphs["s1"].last_accessed_at = time.time() - 10
        removed = store.cleanup_expired()
        assert removed == 1
        assert store.get_session_graph("s2") is not None

    def test_cleanup_keeps_fresh(self) -> None:
        store = SessionGraphStore(ttl_seconds=3600)
        store.add_step("s1", step_number=1)
        removed = store.cleanup_expired()
        assert removed == 0

    def test_get_session_graph_expired(self) -> None:
        store = SessionGraphStore(ttl_seconds=1)
        store.add_step("s1", step_number=1)
        store._graphs["s1"].last_accessed_at = time.time() - 10
        assert store.get_session_graph("s1") is None
