"""Context dependency classifier — classifies how a request depends on prior context.

Uses fast regex/heuristic checks (<1ms target) to classify dependency level:
- INDEPENDENT: no reference to prior conversation
- PARTIAL: references prior context but can stand alone
- DEPENDENT: requires prior context to make sense
- CRITICAL: must not be cached, must not use cached response
"""

import enum
import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


class DependencyLevel(str, enum.Enum):
    """How strongly a request depends on prior conversation context."""

    INDEPENDENT = "INDEPENDENT"
    PARTIAL = "PARTIAL"
    DEPENDENT = "DEPENDENT"
    CRITICAL = "CRITICAL"


@dataclass
class DependencyClassification:
    """Result of dependency classification."""

    level: DependencyLevel
    confidence: float
    signals: list[str] = field(default_factory=list)


# Precompiled patterns for performance (<1ms target)

# CRITICAL: action verbs that require fresh execution
# Also includes revision/update workflows that should never use stale cached responses
_CRITICAL_PATTERNS = [
    re.compile(r"\b(execute|deploy|run|send|delete|drop|remove|kill|terminate|push|publish)\b", re.IGNORECASE),
    re.compile(r"\b(do it now|make it happen|go ahead|proceed|confirm and)\b", re.IGNORECASE),
    re.compile(r"\b(revise|update|improve|address|incorporate|reflect)\s+(the|this|my|your)\s+(comment|feedback|review|response|answer|suggestion)\b", re.IGNORECASE),
    re.compile(r"\b(write|post|create|generate)\s+(a|an|the)?\s*(new|updated|revised|different)\s+(comment|response|reply|message|ticket|issue)\b", re.IGNORECASE),
    re.compile(r"\b(based on|given|considering)\s+(the|this|my)?\s*(latest|new|recent|updated)\s+(feedback|comment|review|input|state)\b", re.IGNORECASE),
]

# DEPENDENT: strong references to prior context that require it
_DEPENDENT_PATTERNS = [
    re.compile(r"\b(the (?:code|function|class|snippet|example|output|result|error) (?:above|below|earlier|before|previously))\b", re.IGNORECASE),
    re.compile(r"\b(apply (?:that|this|it) to)\b", re.IGNORECASE),
    re.compile(r"\b(based on (?:what you|the previous|the above|the earlier|our))\b", re.IGNORECASE),
    re.compile(r"\b(modify|update|fix|change|refactor) (?:the |that |this |it )\b", re.IGNORECASE),
    re.compile(r"\b(as (?:we|you|I) (?:discussed|mentioned|said|noted))\b", re.IGNORECASE),
    re.compile(r"\b(my (?:code|function|class|script|file|project) (?:above|earlier))\b", re.IGNORECASE),
    re.compile(r"\b(from (?:the |my )?(?:previous|earlier|last|above))\b", re.IGNORECASE),
]

# PARTIAL: references that suggest context but the request can stand alone
_PARTIAL_PATTERNS = [
    re.compile(r"\b(tell me more|elaborate|expand on|go deeper)\b", re.IGNORECASE),
    re.compile(r"\b(also|additionally|furthermore|moreover|in addition)\b", re.IGNORECASE),
    re.compile(r"\b(what about|how about|and also|next step)\b", re.IGNORECASE),
    re.compile(r"\b(that|those|these|it|them)\b(?!\s+(?:is|are|was|were)\s+(?:a|an|the))", re.IGNORECASE),
    re.compile(r"\b(continue|keep going|go on|more details)\b", re.IGNORECASE),
]


_ENTITY_RE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")

# Common words that look like entities but aren't.
_ENTITY_SKIP = {
    "the", "this", "that", "what", "how", "when", "where", "which",
    "explain", "describe", "compare", "analyze", "list", "show", "tell",
    "give", "make", "find", "write", "create", "build", "define", "use",
    "return", "please", "also", "just", "now", "here", "there",
}


class DependencyClassifier:
    """Classifies request dependency on prior context using regex heuristics."""

    def classify(
        self,
        prompt: str,
        session_step: Optional[int] = None,
        prior_outputs: Optional[list[str]] = None,
    ) -> DependencyClassification:
        """Classify the dependency level of a prompt.

        Args:
            prompt: The user's prompt text.
            session_step: Current step number in session. Step 1 is always INDEPENDENT.
            prior_outputs: Prior session outputs for content/entity matching.

        Returns:
            DependencyClassification with level, confidence, and matched signals.
        """
        # Step 1 is always independent
        if session_step is not None and session_step <= 1:
            return DependencyClassification(
                level=DependencyLevel.INDEPENDENT,
                confidence=1.0,
                signals=["first_step"],
            )

        signals: list[str] = []

        # Check CRITICAL patterns first (highest priority)
        for pattern in _CRITICAL_PATTERNS:
            match = pattern.search(prompt)
            if match:
                signals.append(f"critical:{match.group()}")

        if signals:
            return DependencyClassification(
                level=DependencyLevel.CRITICAL,
                confidence=min(1.0, 0.7 + len(signals) * 0.1),
                signals=signals,
            )

        # Check DEPENDENT patterns
        for pattern in _DEPENDENT_PATTERNS:
            match = pattern.search(prompt)
            if match:
                signals.append(f"dependent:{match.group()}")

        if len(signals) >= 2:
            return DependencyClassification(
                level=DependencyLevel.DEPENDENT,
                confidence=min(1.0, 0.6 + len(signals) * 0.1),
                signals=signals,
            )

        if len(signals) == 1:
            return DependencyClassification(
                level=DependencyLevel.DEPENDENT,
                confidence=0.65,
                signals=signals,
            )

        # Check PARTIAL patterns
        for pattern in _PARTIAL_PATTERNS:
            match = pattern.search(prompt)
            if match:
                signals.append(f"partial:{match.group()}")

        # --- Enhanced detectors (prior_outputs required) ---
        if prior_outputs and session_step and session_step > 1:
            signals.extend(self._detect_prior_content(prompt, prior_outputs))
            signals.extend(self._count_entity_references(prompt, prior_outputs))

        # Sequence depth scoring
        depth_boost = 0.0
        if session_step and session_step > 1:
            depth_boost, depth_signal = self._score_sequence_depth(session_step)
            if depth_boost > 0:
                signals.append(depth_signal)

        if signals:
            # Combine signal count and depth for classification
            base_confidence = min(1.0, 0.5 + len(signals) * 0.1 + depth_boost)
            # Upgrade to DEPENDENT if many signals
            if len(signals) >= 3 or depth_boost >= 0.2:
                return DependencyClassification(
                    level=DependencyLevel.DEPENDENT,
                    confidence=min(1.0, base_confidence),
                    signals=signals,
                )
            return DependencyClassification(
                level=DependencyLevel.PARTIAL,
                confidence=base_confidence,
                signals=signals,
            )

        # No dependency signals found
        return DependencyClassification(
            level=DependencyLevel.INDEPENDENT,
            confidence=0.8,
            signals=["no_signals"],
        )

    @staticmethod
    def _detect_prior_content(prompt: str, prior_outputs: list[str]) -> list[str]:
        """Check if prompt contains verbatim 3-word fragments from prior outputs."""
        signals: list[str] = []
        prompt_lower = prompt.lower()
        for i, output in enumerate(prior_outputs):
            words = output.lower().split()
            for j in range(len(words) - 2):
                fragment = " ".join(words[j : j + 3])
                if len(fragment) > 10 and fragment in prompt_lower:
                    signals.append(f"prior_content:step{i + 1}:'{fragment[:30]}'")
                    break  # one match per output is enough
        return signals

    @staticmethod
    def _score_sequence_depth(session_step: int) -> tuple[float, str]:
        """Score dependency likelihood based on conversation depth."""
        if session_step <= 1:
            return 0.0, "depth:step1"
        elif session_step <= 3:
            return 0.1, f"depth:early_step{session_step}"
        elif session_step <= 7:
            return 0.2, f"depth:mid_step{session_step}"
        else:
            return 0.3, f"depth:deep_step{session_step}"

    @staticmethod
    def _count_entity_references(prompt: str, prior_outputs: list[str]) -> list[str]:
        """Find named entities from prior outputs that appear in current prompt."""
        prior_entities: set[str] = set()
        for output in prior_outputs:
            for match in _ENTITY_RE.finditer(output):
                entity = match.group().lower()
                if len(entity) > 3 and entity not in _ENTITY_SKIP:
                    prior_entities.add(entity)

        signals: list[str] = []
        prompt_lower = prompt.lower()
        for entity in prior_entities:
            if entity in prompt_lower:
                signals.append(f"entity_ref:{entity}")
        return signals


def build_dependency_fingerprint(
    dependency_levels: list[str],
    session_step: Optional[int] = None,
) -> str:
    """Build a stable fingerprint from sorted dependency classifications.

    This fingerprint is used as a cache key suffix so that requests with
    different dependency contexts hit different cache entries.

    Args:
        dependency_levels: List of DependencyLevel values from prior steps
            in the session (e.g. ["INDEPENDENT", "PARTIAL", "DEPENDENT"]).
        session_step: Current step number (optional, included in hash).

    Returns:
        A 16-character hex digest (first 16 chars of SHA-256).
    """
    sorted_levels = sorted(dependency_levels)
    payload = "|".join(sorted_levels)
    if session_step is not None:
        payload += f"|step:{session_step}"
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
