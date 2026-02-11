"""Tests for ConstraintInterpreter."""

import pytest

from src.routing.constraints import ConstraintInterpreter
from src.routing.constraints import RoutingConstraints


@pytest.fixture
def interpreter() -> ConstraintInterpreter:
    return ConstraintInterpreter()


class TestInterpret:
    """Tests for ConstraintInterpreter.interpret."""

    def test_defaults(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret()
        assert isinstance(c, RoutingConstraints)
        assert c.quality_threshold == 3.5
        assert c.latency_budget_ms == 500

    def test_quality_low(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret(quality_preference="low")
        assert c.quality_threshold == 3.0

    def test_quality_max(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret(quality_preference="max")
        assert c.quality_threshold == 4.5

    def test_latency_fast(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret(latency_preference="fast")
        assert c.latency_budget_ms == 300

    def test_latency_instant(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret(latency_preference="instant")
        assert c.latency_budget_ms == 150

    def test_coding_override_raises_quality(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret(
            quality_preference="low", task_type="coding"
        )
        # Coding overrides min quality to 4.0
        assert c.quality_threshold == 4.0

    def test_legal_override(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret(
            quality_preference="medium", task_type="legal"
        )
        # Legal overrides min quality to 4.2
        assert c.quality_threshold == 4.2

    def test_invalid_quality_raises(self, interpreter: ConstraintInterpreter) -> None:
        with pytest.raises(ValueError, match="quality_preference"):
            interpreter.interpret(quality_preference="ultra")

    def test_invalid_latency_raises(self, interpreter: ConstraintInterpreter) -> None:
        with pytest.raises(ValueError, match="latency_preference"):
            interpreter.interpret(latency_preference="ludicrous")

    def test_general_task_no_override(self, interpreter: ConstraintInterpreter) -> None:
        c = interpreter.interpret(
            quality_preference="low",
            latency_preference="slow",
            task_type="general",
        )
        assert c.quality_threshold == 3.0
        assert c.latency_budget_ms == 2000
