"""
Workflow decomposer for Asahi Tier 3 intermediate caching.

Breaks complex requests into discrete steps, each of which can be
cached independently.  This enables intermediate result reuse across
different queries that share common sub-tasks.
"""

import hashlib
import logging
import re
from typing import List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WorkflowStep(BaseModel):
    """A single step in a decomposed workflow.

    Attributes:
        step_id: Unique identifier for this step.
        step_type: Category of the step (summarize, extract, classify, answer).
        intent: Specific intent within the type.
        document_id: Optional document reference.
        input_text: The text input for this step.
        cache_key: Composite key for caching: ``{doc_id}:{step_type}:{intent_hash}``.
        result: Filled after execution or cache hit.
    """

    step_id: str
    step_type: str
    intent: str
    document_id: Optional[str] = None
    input_text: str
    cache_key: str
    result: Optional[str] = None


class WorkflowConfig(BaseModel):
    """Configuration for the workflow decomposer.

    Attributes:
        max_steps: Maximum number of steps to generate.
        enable_document_decomposition: Whether to split by document sections.
    """

    max_steps: int = Field(default=10, gt=0)
    enable_document_decomposition: bool = True


class WorkflowDecomposer:
    """Decompose complex prompts into cacheable workflow steps.

    Detects multi-part questions, document references, and comparison
    patterns to generate independent steps that can be cached and
    reused across requests.

    Args:
        config: Decomposition configuration.
    """

    def __init__(self, config: WorkflowConfig | None = None) -> None:
        self._config = config or WorkflowConfig()

    def decompose(
        self,
        prompt: str,
        document_id: Optional[str] = None,
        task_type: Optional[str] = None,
    ) -> List[WorkflowStep]:
        """Decompose a prompt into workflow steps.

        Rules:
        - Single question, no document: 1 step (direct answer).
        - Question with document reference: 2 steps (summarise + answer).
        - Multi-part question: N steps (one per sub-question).
        - Comparison question: 3 steps (summarise A, summarise B, compare).

        Args:
            prompt: The user query to decompose.
            document_id: Optional document identifier.
            task_type: Optional task type hint.

        Returns:
            List of WorkflowStep objects.
        """
        if not prompt or not prompt.strip():
            return []

        prompt = prompt.strip()

        # Detect comparison pattern
        if self._is_comparison(prompt):
            return self._decompose_comparison(prompt, document_id)

        # Detect multi-part questions
        parts = self._split_multi_part(prompt)
        if len(parts) > 1:
            return self._decompose_multi_part(parts, document_id)

        # Detect document reference
        if document_id or self._has_document_reference(prompt):
            doc_id = document_id or self._extract_document_id(prompt)
            return self._decompose_with_document(prompt, doc_id)

        # Single direct question
        return [
            self._make_step(
                step_type="answer",
                intent=self.extract_intent(prompt),
                input_text=prompt,
                document_id=document_id,
                step_num=1,
            )
        ]

    def extract_intent(self, text: str) -> str:
        """Extract a brief intent description from the text.

        Args:
            text: Input text.

        Returns:
            Short intent string.
        """
        text = text.strip()
        # Take first sentence or first 80 chars
        first_sentence = re.split(r"[.!?]", text)[0].strip()
        if len(first_sentence) > 80:
            first_sentence = first_sentence[:77] + "..."
        return first_sentence

    def extract_document_sections(self, text: str) -> List[str]:
        """Extract distinct sections from a document-like text.

        Splits on common section markers (numbered sections,
        headings, double newlines).

        Args:
            text: Input text.

        Returns:
            List of section strings.
        """
        # Split on numbered sections or double newlines
        sections = re.split(
            r"\n\s*(?:\d+[\.\)]\s|#{1,3}\s|\n)", text
        )
        sections = [s.strip() for s in sections if s.strip()]
        return sections if sections else [text.strip()]

    # ------------------------------------------------------------------
    # Internal decomposition strategies
    # ------------------------------------------------------------------

    def _is_comparison(self, prompt: str) -> bool:
        """Check if the prompt is a comparison question."""
        patterns = [
            r"\bcompare\b",
            r"\bdifference between\b",
            r"\bvs\.?\b",
            r"\bversus\b",
            r"\bcontrast\b",
            r"\bbetter.+or\b",
        ]
        return any(
            re.search(p, prompt, re.IGNORECASE) for p in patterns
        )

    def _decompose_comparison(
        self, prompt: str, document_id: Optional[str]
    ) -> List[WorkflowStep]:
        """Decompose a comparison question into 3 steps."""
        # Try to extract the two subjects
        subjects = self._extract_comparison_subjects(prompt)
        steps: List[WorkflowStep] = []

        if len(subjects) >= 2:
            steps.append(
                self._make_step(
                    step_type="summarize",
                    intent=f"Summarize: {subjects[0]}",
                    input_text=f"Provide key facts about {subjects[0]}",
                    document_id=document_id,
                    step_num=1,
                )
            )
            steps.append(
                self._make_step(
                    step_type="summarize",
                    intent=f"Summarize: {subjects[1]}",
                    input_text=f"Provide key facts about {subjects[1]}",
                    document_id=document_id,
                    step_num=2,
                )
            )
            steps.append(
                self._make_step(
                    step_type="answer",
                    intent=f"Compare {subjects[0]} vs {subjects[1]}",
                    input_text=prompt,
                    document_id=document_id,
                    step_num=3,
                )
            )
        else:
            # Can't split subjects, treat as single step
            steps.append(
                self._make_step(
                    step_type="answer",
                    intent=self.extract_intent(prompt),
                    input_text=prompt,
                    document_id=document_id,
                    step_num=1,
                )
            )

        return steps[: self._config.max_steps]

    def _extract_comparison_subjects(self, prompt: str) -> List[str]:
        """Extract the two subjects being compared."""
        # Pattern: "compare X and Y", "X vs Y", "difference between X and Y"
        patterns = [
            r"compare\s+(.+?)\s+(?:and|with|to)\s+(.+?)(?:\.|$|\?)",
            r"difference\s+between\s+(.+?)\s+and\s+(.+?)(?:\.|$|\?)",
            r"(.+?)\s+vs\.?\s+(.+?)(?:\.|$|\?)",
            r"(.+?)\s+versus\s+(.+?)(?:\.|$|\?)",
        ]
        for pattern in patterns:
            match = re.search(pattern, prompt, re.IGNORECASE)
            if match:
                return [match.group(1).strip(), match.group(2).strip()]
        return []

    def _split_multi_part(self, prompt: str) -> List[str]:
        """Split a multi-part question into parts."""
        # Split on numbered lists, semicolons, or "and also" / "additionally"
        parts: List[str] = []

        # Try numbered list
        numbered = re.split(r"\d+[\.\)]\s+", prompt)
        numbered = [p.strip() for p in numbered if p.strip()]
        if len(numbered) > 1:
            return numbered

        # Try question mark splits (multiple questions)
        questions = [
            p.strip() + "?" for p in prompt.split("?") if p.strip()
        ]
        if len(questions) > 1:
            return questions

        return [prompt]

    def _decompose_multi_part(
        self, parts: List[str], document_id: Optional[str]
    ) -> List[WorkflowStep]:
        """Create one step per sub-question."""
        steps: List[WorkflowStep] = []
        for i, part in enumerate(parts):
            steps.append(
                self._make_step(
                    step_type="answer",
                    intent=self.extract_intent(part),
                    input_text=part,
                    document_id=document_id,
                    step_num=i + 1,
                )
            )
        return steps[: self._config.max_steps]

    def _has_document_reference(self, prompt: str) -> bool:
        """Check if the prompt references a document."""
        patterns = [
            r"\b(document|article|paper|text|passage|section|paragraph)\b",
            r"\b(based on|according to|from the|in the)\b",
        ]
        return any(
            re.search(p, prompt, re.IGNORECASE) for p in patterns
        )

    def _extract_document_id(self, prompt: str) -> str:
        """Extract or generate a document ID from the prompt."""
        # Hash the prompt to create a stable document ID
        return hashlib.md5(prompt.encode()).hexdigest()[:12]

    def _decompose_with_document(
        self, prompt: str, document_id: Optional[str]
    ) -> List[WorkflowStep]:
        """Decompose a document-referenced query into 2 steps."""
        return [
            self._make_step(
                step_type="summarize",
                intent="Summarize relevant section",
                input_text=prompt,
                document_id=document_id,
                step_num=1,
            ),
            self._make_step(
                step_type="answer",
                intent=self.extract_intent(prompt),
                input_text=prompt,
                document_id=document_id,
                step_num=2,
            ),
        ]

    def _make_step(
        self,
        step_type: str,
        intent: str,
        input_text: str,
        document_id: Optional[str],
        step_num: int,
    ) -> WorkflowStep:
        """Create a WorkflowStep with a deterministic cache key.

        Args:
            step_type: Step category.
            intent: Brief intent description.
            input_text: Input text for the step.
            document_id: Optional document ID.
            step_num: Step number in the workflow.

        Returns:
            Constructed WorkflowStep.
        """
        doc_part = document_id or "none"
        intent_hash = hashlib.md5(intent.encode()).hexdigest()[:8]
        cache_key = f"{doc_part}:{step_type}:{intent_hash}"

        return WorkflowStep(
            step_id=f"step_{step_num}",
            step_type=step_type,
            intent=intent,
            document_id=document_id,
            input_text=input_text,
            cache_key=cache_key,
        )
