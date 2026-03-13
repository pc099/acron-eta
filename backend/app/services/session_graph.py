"""Session graph store — tracks step dependencies within agent sessions.

Maintains an in-memory directed graph of session steps. Each step records
which prior steps it depends on and references the CallTrace that produced it.

In production, this will be backed by Redis hashes with TTL.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class StepNode:
    """A single step in a session graph."""

    step_number: int
    call_trace_id: Optional[str] = None
    depends_on: list[int] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)


@dataclass
class SessionGraph:
    """Full graph of steps for a session."""

    session_id: str
    steps: dict[int, StepNode] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)

    @property
    def step_count(self) -> int:
        """Return the number of steps in this session."""
        return len(self.steps)

    @property
    def latest_step(self) -> Optional[int]:
        """Return the highest step number, or None if empty."""
        return max(self.steps.keys()) if self.steps else None


class SessionGraphStore:
    """In-memory session graph store.

    Thread-safe for single-process use. In production, replace with
    Redis HSET/HGET for distributed access.
    """

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._graphs: dict[str, SessionGraph] = {}
        self._ttl_seconds = ttl_seconds

    def add_step(
        self,
        session_id: str,
        step_number: int,
        call_trace_id: Optional[str] = None,
        depends_on: Optional[list[int]] = None,
        metadata: Optional[dict] = None,
    ) -> StepNode:
        """Record a new step in the session graph.

        Args:
            session_id: The session identifier.
            step_number: The step number (must be positive).
            call_trace_id: ID of the CallTrace for this step.
            depends_on: List of step numbers this step depends on.
            metadata: Additional metadata for this step.

        Returns:
            The created StepNode.

        Raises:
            ValueError: If step_number is not positive or depends_on references unknown steps.
        """
        if step_number < 1:
            raise ValueError(f"Step number must be positive, got {step_number}")

        graph = self._graphs.setdefault(session_id, SessionGraph(session_id=session_id))
        graph.last_accessed_at = time.time()

        # Validate dependencies exist
        deps = depends_on or []
        for dep in deps:
            if dep not in graph.steps and dep != step_number:
                logger.warning(
                    "Step %d depends on unknown step %d in session %s",
                    step_number, dep, session_id,
                )

        node = StepNode(
            step_number=step_number,
            call_trace_id=call_trace_id,
            depends_on=deps,
            metadata=metadata or {},
        )
        graph.steps[step_number] = node

        logger.debug(
            "Added step %d to session %s (depends_on=%s)",
            step_number, session_id, deps,
        )
        return node

    def _get_live_graph(self, session_id: str) -> Optional[SessionGraph]:
        """Return the graph if it exists and is not expired, else None."""
        graph = self._graphs.get(session_id)
        if not graph:
            return None
        if time.time() - graph.last_accessed_at > self._ttl_seconds:
            del self._graphs[session_id]
            logger.debug("Session %s expired (TTL=%ds)", session_id, self._ttl_seconds)
            return None
        graph.last_accessed_at = time.time()
        return graph

    def get_step(self, session_id: str, step_number: int) -> Optional[StepNode]:
        """Get a specific step from a session graph."""
        graph = self._get_live_graph(session_id)
        if not graph:
            return None
        return graph.steps.get(step_number)

    def get_dependencies(self, session_id: str, step_number: int) -> list[StepNode]:
        """Get all steps that the given step depends on (transitive)."""
        graph = self._get_live_graph(session_id)
        if not graph:
            return []

        node = graph.steps.get(step_number)
        if not node:
            return []

        visited: set[int] = set()
        result: list[StepNode] = []
        self._collect_deps(graph, node.depends_on, visited, result)
        return result

    def _collect_deps(
        self,
        graph: SessionGraph,
        deps: list[int],
        visited: set[int],
        result: list[StepNode],
    ) -> None:
        """Recursively collect transitive dependencies."""
        for dep_num in deps:
            if dep_num in visited:
                continue
            visited.add(dep_num)
            dep_node = graph.steps.get(dep_num)
            if dep_node:
                result.append(dep_node)
                self._collect_deps(graph, dep_node.depends_on, visited, result)

    def get_session_graph(self, session_id: str) -> Optional[SessionGraph]:
        """Get the full session graph."""
        return self._get_live_graph(session_id)

    def cleanup_expired(self) -> int:
        """Remove all expired session graphs. Returns count removed."""
        now = time.time()
        expired = [
            sid for sid, graph in self._graphs.items()
            if now - graph.last_accessed_at > self._ttl_seconds
        ]
        for sid in expired:
            del self._graphs[sid]
        if expired:
            logger.info("Cleaned up %d expired session graphs", len(expired))
        return len(expired)

    def remove_session(self, session_id: str) -> bool:
        """Remove a session graph from the store."""
        return self._graphs.pop(session_id, None) is not None
