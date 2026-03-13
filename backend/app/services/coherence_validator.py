"""Context coherence validator — checks if a cached response fits the current context.

Four fast checks (<2ms total budget):
1. Format continuity — request format matches cache format
2. Entity consistency — key entities from request appear in cache response
3. Temporal freshness — time-sensitive requests reject stale cache
4. Step compatibility — session step context matches cache context

Returns CoherenceResult with is_coherent flag, score, and failed checks.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CoherenceResult:
    """Result of coherence validation."""

    is_coherent: bool
    score: float  # 0.0 = no coherence, 1.0 = perfect coherence
    failed_checks: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0


@dataclass
class CoherenceMetrics:
    """Accumulated metrics for coherence validation."""

    total_checks: int = 0
    passed: int = 0
    failed: int = 0
    per_check_failures: dict[str, int] = field(default_factory=lambda: {
        "format_continuity": 0,
        "entity_consistency": 0,
        "temporal_freshness": 0,
        "step_compatibility": 0,
    })

    @property
    def pass_rate(self) -> float:
        """Return the pass rate as a float (0.0 - 1.0)."""
        return self.passed / self.total_checks if self.total_checks > 0 else 0.0

    def to_dict(self) -> dict:
        """Serialize metrics to a dict."""
        return {
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 4),
            "per_check_failures": dict(self.per_check_failures),
        }


# Precompiled patterns
_JSON_REQUEST = re.compile(r"\b(json|JSON|structured|schema)\b", re.IGNORECASE)
_CODE_REQUEST = re.compile(r"\b(code|function|class|implement|script|program)\b", re.IGNORECASE)
_LIST_REQUEST = re.compile(r"\b(list|bullet|enumerate|items)\b", re.IGNORECASE)
_TEMPORAL_PATTERNS = re.compile(
    r"\b(today|now|current|latest|recent|this (?:week|month|year)|right now|at the moment)\b",
    re.IGNORECASE,
)
_ENTITY_PATTERN = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")
_QUOTED_TERMS = re.compile(r'"([^"]+)"|\'([^\']+)\'')


class CoherenceValidator:
    """Validates whether a cached response is coherent with the current request context."""

    def __init__(
        self,
        max_cache_age_seconds: int = 86400,
        temporal_max_age_seconds: int = 3600,
        coherence_threshold: float = 0.5,
    ) -> None:
        self._max_cache_age = max_cache_age_seconds
        self._temporal_max_age = temporal_max_age_seconds
        self._threshold = coherence_threshold
        self._metrics = CoherenceMetrics()

    def validate(
        self,
        request_prompt: str,
        cached_response: str,
        cache_age_seconds: float = 0.0,
        request_step: Optional[int] = None,
        cache_step: Optional[int] = None,
    ) -> CoherenceResult:
        """Run all coherence checks on a cached response.

        Args:
            request_prompt: The current request prompt.
            cached_response: The cached response text.
            cache_age_seconds: How old the cache entry is in seconds.
            request_step: Current session step number.
            cache_step: Step number when cache was created.

        Returns:
            CoherenceResult with pass/fail and details.
        """
        start = time.perf_counter()
        checks_passed = 0
        checks_total = 0
        failed: list[str] = []

        # Check 1: Format continuity
        checks_total += 1
        if self._check_format_continuity(request_prompt, cached_response):
            checks_passed += 1
        else:
            failed.append("format_continuity")

        # Check 2: Entity consistency
        checks_total += 1
        if self._check_entity_consistency(request_prompt, cached_response):
            checks_passed += 1
        else:
            failed.append("entity_consistency")

        # Check 3: Temporal freshness
        checks_total += 1
        if self._check_temporal_freshness(request_prompt, cache_age_seconds):
            checks_passed += 1
        else:
            failed.append("temporal_freshness")

        # Check 4: Step compatibility
        if request_step is not None and cache_step is not None:
            checks_total += 1
            if self._check_step_compatibility(request_step, cache_step):
                checks_passed += 1
            else:
                failed.append("step_compatibility")

        score = checks_passed / checks_total if checks_total > 0 else 0.0
        elapsed = (time.perf_counter() - start) * 1000

        result = CoherenceResult(
            is_coherent=score >= self._threshold,
            score=round(score, 4),
            failed_checks=failed,
            elapsed_ms=round(elapsed, 3),
        )

        # Track metrics
        self._metrics.total_checks += 1
        if result.is_coherent:
            self._metrics.passed += 1
        else:
            self._metrics.failed += 1
            for check_name in result.failed_checks:
                if check_name in self._metrics.per_check_failures:
                    self._metrics.per_check_failures[check_name] += 1

        return result

    def _check_format_continuity(self, prompt: str, cached: str) -> bool:
        """Check if the cached response format matches what the request expects."""
        # If request asks for JSON, cached response should contain JSON-like content
        if _JSON_REQUEST.search(prompt):
            if "{" not in cached and "[" not in cached:
                return False

        # If request asks for code, cached should contain code markers
        if _CODE_REQUEST.search(prompt):
            if "```" not in cached and "def " not in cached and "class " not in cached:
                # Lenient: code-like content is OK
                pass  # Don't fail — code can appear in many forms

        return True

    def _check_entity_consistency(self, prompt: str, cached: str) -> bool:
        """Check if key entities from the request appear in the cached response."""
        # Extract quoted terms (highest signal)
        quoted = set()
        for match in _QUOTED_TERMS.finditer(prompt):
            term = match.group(1) or match.group(2)
            quoted.add(term.lower())

        # Extract capitalized entities (proper nouns, tech names)
        entities = set()
        for match in _ENTITY_PATTERN.finditer(prompt):
            entity = match.group()
            # Skip common words and verbs that appear at sentence starts
            if entity.lower() not in {
                "the", "this", "that", "what", "how", "can", "will",
                "explain", "describe", "compare", "analyze", "list",
                "show", "tell", "give", "make", "find", "write",
                "create", "build", "define", "return", "use",
            }:
                entities.add(entity.lower())

        # If no entities found, pass by default
        if not quoted and not entities:
            return True

        cached_lower = cached.lower()

        # Check quoted terms (must all be present)
        for term in quoted:
            if term not in cached_lower:
                return False

        # Check entities (at least half should be present)
        if entities:
            found = sum(1 for e in entities if e in cached_lower)
            if found < len(entities) * 0.5:
                return False

        return True

    def _check_temporal_freshness(self, prompt: str, cache_age_seconds: float) -> bool:
        """Check if time-sensitive requests are served from fresh cache."""
        if _TEMPORAL_PATTERNS.search(prompt):
            return cache_age_seconds <= self._temporal_max_age
        return cache_age_seconds <= self._max_cache_age

    def _check_step_compatibility(self, request_step: int, cache_step: int) -> bool:
        """Check if the cache was created in a compatible session step context."""
        # Cache from the same step or an earlier step in the same session is compatible
        # Cache from a much later step is not (context has diverged)
        return cache_step <= request_step

    @property
    def metrics(self) -> CoherenceMetrics:
        """Return accumulated coherence validation metrics."""
        return self._metrics
