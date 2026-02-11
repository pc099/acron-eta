"""
Task type detection for Asahi inference optimizer.

Automatically detects the task type (summarization, reasoning, faq,
coding, etc.) from the user's prompt using keyword/pattern matching.
Used by AUTOPILOT routing mode and adaptive threshold tuning.
"""

import logging
import re
from typing import Dict, List, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class TaskDetection(BaseModel):
    """Result of task type detection.

    Attributes:
        task_type: Detected task category.
        confidence: Detection confidence from 0.0 to 1.0.
        intent: Brief description of the detected intent.
    """

    task_type: str = "general"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    intent: str = ""


# Pattern definitions: (compiled regex, task_type, intent_description)
_PATTERNS: List[Tuple[re.Pattern, str, str]] = [
    (
        re.compile(
            r"\b(summarize|summary|summarise|tldr|brief|overview|recap)\b",
            re.IGNORECASE,
        ),
        "summarization",
        "Summarize content",
    ),
    (
        re.compile(
            r"\b(why|explain|reason|analyze|analyse|because|cause|understand)\b",
            re.IGNORECASE,
        ),
        "reasoning",
        "Explain or reason about something",
    ),
    (
        re.compile(
            r"\b(how do i|what is|what are|who is|where is|when did|help with|tell me about)\b",
            re.IGNORECASE,
        ),
        "faq",
        "Answer a factual question",
    ),
    (
        re.compile(
            r"\b(write code|implement|function|class|def |import |python|javascript|"
            r"typescript|java\b|debug|fix this code|refactor|algorithm)\b",
            re.IGNORECASE,
        ),
        "coding",
        "Write or modify code",
    ),
    (
        re.compile(
            r"\b(translate|convert to|in spanish|in french|in german|in japanese|"
            r"in chinese|in korean|translation)\b",
            re.IGNORECASE,
        ),
        "translation",
        "Translate text between languages",
    ),
    (
        re.compile(
            r"\b(classify|categorize|categorise|sentiment|label|tag)\b",
            re.IGNORECASE,
        ),
        "classification",
        "Classify or categorize content",
    ),
    (
        re.compile(
            r"\b(write a poem|write a story|creative|haiku|limerick|"
            r"fiction|compose|lyrics)\b",
            re.IGNORECASE,
        ),
        "creative",
        "Generate creative content",
    ),
    (
        re.compile(
            r"\b(legal|contract|statute|regulation|compliance|attorney|lawyer)\b",
            re.IGNORECASE,
        ),
        "legal",
        "Legal analysis or review",
    ),
]


class TaskTypeDetector:
    """Detect task type from a user prompt using keyword/pattern matching.

    Uses a set of compiled regex patterns to identify the most likely
    task category.  Confidence is proportional to the number of
    distinct pattern matches found.
    """

    def __init__(self) -> None:
        self._patterns = _PATTERNS

    def detect(self, prompt: str) -> TaskDetection:
        """Detect the task type of a prompt.

        Args:
            prompt: The user query to classify.

        Returns:
            TaskDetection with the detected type, confidence, and intent.
        """
        if not prompt or not prompt.strip():
            return TaskDetection(
                task_type="general",
                confidence=0.0,
                intent="Empty or blank prompt",
            )

        matches: Dict[str, Tuple[int, str]] = {}

        for pattern, task_type, intent in self._patterns:
            found = pattern.findall(prompt)
            if found:
                count = len(found)
                if task_type not in matches or count > matches[task_type][0]:
                    matches[task_type] = (count, intent)

        if not matches:
            return TaskDetection(
                task_type="general",
                confidence=0.1,
                intent="No strong pattern match; defaulting to general",
            )

        # Pick the task type with the most matches
        best_type = max(matches, key=lambda t: matches[t][0])
        best_count = matches[best_type][0]
        best_intent = matches[best_type][1]

        # Confidence: scale from 0.3 (1 match) to 0.95 (4+ matches)
        confidence = min(0.95, 0.3 + (best_count - 1) * 0.2)

        # If multiple task types matched, reduce confidence slightly
        if len(matches) > 1:
            confidence *= 0.9

        logger.debug(
            "Task type detected",
            extra={
                "task_type": best_type,
                "confidence": round(confidence, 2),
                "matches": {k: v[0] for k, v in matches.items()},
            },
        )

        return TaskDetection(
            task_type=best_type,
            confidence=round(confidence, 2),
            intent=best_intent,
        )
