"""
Token optimizer pipeline for Asahi inference cost reduction.

Orchestrates context analysis, prompt compression, and few-shot
selection into a single optimization pass.  Calculates token savings
and assesses quality risk.
"""

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.models.registry import estimate_tokens
from src.optimization.analyzer import AnalyzerConfig, ContextAnalyzer, SegmentScore
from src.optimization.compressor import CompressorConfig, PromptCompressor
from src.optimization.few_shot import FewShotSelector

logger = logging.getLogger(__name__)


class OptimizerConfig(BaseModel):
    """Configuration for the TokenOptimizer pipeline.

    Attributes:
        max_quality_risk: Maximum acceptable quality risk level.
            If optimization would exceed this, it is skipped.
        enable_context_analysis: Whether to run relevance filtering.
        enable_compression: Whether to run prompt compression.
        enable_few_shot_selection: Whether to run few-shot selection.
        max_few_shot_examples: Max examples to keep after selection.
    """

    max_quality_risk: Literal["none", "low", "medium", "high"] = "medium"
    enable_context_analysis: bool = True
    enable_compression: bool = True
    enable_few_shot_selection: bool = True
    max_few_shot_examples: int = Field(default=3, ge=1)


class OptimizationResult(BaseModel):
    """Result of the full optimization pipeline.

    Attributes:
        original_prompt: The complete prompt before optimization.
        optimized_prompt: The prompt after all optimization steps.
        original_tokens: Token count before optimization.
        optimized_tokens: Token count after optimization.
        tokens_saved: Number of tokens removed.
        savings_percent: Percentage of tokens saved.
        strategies_applied: List of strategies that were used.
        quality_risk: Assessed risk of quality degradation.
    """

    original_prompt: str
    optimized_prompt: str
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    savings_percent: float = Field(ge=0.0)
    strategies_applied: List[str]
    quality_risk: Literal["none", "low", "medium", "high"]


# Risk level ordering for comparison
_RISK_ORDER: Dict[str, int] = {
    "none": 0,
    "low": 1,
    "medium": 2,
    "high": 3,
}


class TokenOptimizer:
    """End-to-end token optimization pipeline.

    Combines context analysis, compression, and few-shot selection
    to reduce prompt token count while managing quality risk.

    Args:
        analyzer: Segment relevance scorer.
        compressor: Prompt compression engine.
        few_shot_selector: Few-shot example picker (optional).
        config: Pipeline configuration.
    """

    def __init__(
        self,
        analyzer: ContextAnalyzer,
        compressor: PromptCompressor,
        few_shot_selector: Optional[FewShotSelector] = None,
        config: Optional[OptimizerConfig] = None,
    ) -> None:
        self._analyzer = analyzer
        self._compressor = compressor
        self._few_shot_selector = few_shot_selector
        self._config = config or OptimizerConfig()

        logger.info(
            "TokenOptimizer initialised",
            extra={
                "context_analysis": self._config.enable_context_analysis,
                "compression": self._config.enable_compression,
                "few_shot": self._config.enable_few_shot_selection,
                "max_risk": self._config.max_quality_risk,
            },
        )

    def optimize(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
        examples: Optional[List[Dict[str, str]]] = None,
        task_type: str = "general",
        quality_preference: str = "medium",
    ) -> OptimizationResult:
        """Run the full optimization pipeline.

        Pipeline steps:
            1. Parse prompt into segments.
            2. Analyze relevance of each segment.
            3. Remove segments below threshold.
            4. Compress remaining segments.
            5. Select best few-shot examples.
            6. Reassemble optimized prompt.
            7. Assess quality risk.

        Args:
            prompt: The user's query / main prompt.
            system_prompt: Optional system prompt text.
            history: Optional chat history as list of dicts with
                ``"role"`` and ``"content"`` keys.
            examples: Optional few-shot examples as list of dicts
                with ``"input"`` and ``"output"`` keys.
            task_type: Task type for context-aware optimization.
            quality_preference: Quality preference level.

        Returns:
            :class:`OptimizationResult` with before/after metrics.
        """
        strategies_applied: List[str] = []

        # Build original prompt from all parts
        original_parts = self._build_prompt_parts(
            prompt, system_prompt, history, examples
        )
        original_prompt = self._assemble_prompt(original_parts)
        original_tokens = estimate_tokens(original_prompt)

        # Working copy of parts to optimize
        optimized_parts = dict(original_parts)

        # Step 1: Context analysis and filtering
        if self._config.enable_context_analysis:
            optimized_parts = self._apply_context_analysis(
                optimized_parts, prompt
            )
            strategies_applied.append("context_analysis")

        # Step 2: Compression
        if self._config.enable_compression:
            optimized_parts = self._apply_compression(
                optimized_parts, prompt
            )
            strategies_applied.append("compression")

        # Step 3: Few-shot selection
        if (
            self._config.enable_few_shot_selection
            and examples
            and self._few_shot_selector is not None
        ):
            selected = self._few_shot_selector.select(
                query=prompt,
                examples=examples,
                max_examples=self._config.max_few_shot_examples,
            )
            optimized_parts["examples"] = self._format_examples(selected)
            strategies_applied.append("few_shot_selection")

        # Reassemble
        optimized_prompt = self._assemble_prompt(optimized_parts)
        optimized_tokens = estimate_tokens(optimized_prompt)
        tokens_saved = max(0, original_tokens - optimized_tokens)
        savings_pct = (
            round((tokens_saved / original_tokens) * 100, 1)
            if original_tokens > 0
            else 0.0
        )

        # Assess quality risk
        quality_risk = self._assess_quality_risk(savings_pct)

        # If risk exceeds max allowed, skip optimization
        if _RISK_ORDER[quality_risk] > _RISK_ORDER[self._config.max_quality_risk]:
            logger.warning(
                "Optimization skipped: risk too high",
                extra={
                    "quality_risk": quality_risk,
                    "max_allowed": self._config.max_quality_risk,
                    "savings_percent": savings_pct,
                },
            )
            return OptimizationResult(
                original_prompt=original_prompt,
                optimized_prompt=original_prompt,
                original_tokens=original_tokens,
                optimized_tokens=original_tokens,
                tokens_saved=0,
                savings_percent=0.0,
                strategies_applied=["skipped_high_risk"],
                quality_risk=quality_risk,
            )

        logger.info(
            "Token optimization complete",
            extra={
                "original_tokens": original_tokens,
                "optimized_tokens": optimized_tokens,
                "savings_percent": savings_pct,
                "quality_risk": quality_risk,
                "strategies": strategies_applied,
            },
        )

        return OptimizationResult(
            original_prompt=original_prompt,
            optimized_prompt=optimized_prompt,
            original_tokens=original_tokens,
            optimized_tokens=optimized_tokens,
            tokens_saved=tokens_saved,
            savings_percent=savings_pct,
            strategies_applied=strategies_applied,
            quality_risk=quality_risk,
        )

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _apply_context_analysis(
        self,
        parts: Dict[str, str],
        query: str,
    ) -> Dict[str, str]:
        """Run context analysis and remove low-relevance segments.

        Args:
            parts: Current prompt parts.
            query: User query for relevance anchor.

        Returns:
            Updated parts with low-relevance content removed.
        """
        segments = self._analyzer.analyze(parts, query)
        filtered = self._analyzer.filter_by_relevance(segments)

        result: Dict[str, str] = {}
        for seg in filtered:
            if seg.category in result:
                result[seg.category] += "\n" + seg.text
            else:
                result[seg.category] = seg.text

        return result

    def _apply_compression(
        self,
        parts: Dict[str, str],
        query: str,
    ) -> Dict[str, str]:
        """Compress each segment using the appropriate strategy.

        Args:
            parts: Current prompt parts.
            query: User query for document compression.

        Returns:
            Updated parts with compressed text.
        """
        result: Dict[str, str] = {}

        for category, text in parts.items():
            if not text or not text.strip():
                continue

            if category == "system":
                compressed = self._compressor.compress_system_prompt(text)
                result[category] = compressed.compressed_text
            elif category == "document":
                compressed = self._compressor.compress_document(text, query)
                result[category] = compressed.compressed_text
            elif category == "query":
                # Never compress the user query
                result[category] = text
            else:
                compressed = self._compressor.compress(text, strategy="extractive")
                result[category] = compressed.compressed_text

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_prompt_parts(
        prompt: str,
        system_prompt: Optional[str],
        history: Optional[List[Dict[str, str]]],
        examples: Optional[List[Dict[str, str]]],
    ) -> Dict[str, str]:
        """Build a dict of prompt parts from the input arguments.

        Args:
            prompt: Main user query.
            system_prompt: Optional system prompt.
            history: Optional chat history.
            examples: Optional few-shot examples.

        Returns:
            Dict keyed by category with text values.
        """
        parts: Dict[str, str] = {"query": prompt}

        if system_prompt:
            parts["system"] = system_prompt

        if history:
            history_parts: List[str] = []
            for turn in history:
                role = turn.get("role", "unknown")
                content = turn.get("content", "")
                history_parts.append(f"{role}: {content}")
            parts["history"] = "\n".join(history_parts)

        if examples:
            example_parts: List[str] = []
            for ex in examples:
                inp = ex.get("input", "")
                out = ex.get("output", "")
                example_parts.append(f"Input: {inp}\nOutput: {out}")
            parts["example"] = "\n\n".join(example_parts)

        return parts

    @staticmethod
    def _format_examples(examples: List[Dict[str, str]]) -> str:
        """Format selected examples back into text.

        Args:
            examples: List of example dicts.

        Returns:
            Formatted example text.
        """
        parts: List[str] = []
        for ex in examples:
            inp = ex.get("input", "")
            out = ex.get("output", "")
            parts.append(f"Input: {inp}\nOutput: {out}")
        return "\n\n".join(parts)

    @staticmethod
    def _assemble_prompt(parts: Dict[str, str]) -> str:
        """Assemble prompt parts into a single string.

        Order: system -> example -> history -> document -> query.

        Args:
            parts: Prompt parts by category.

        Returns:
            Assembled prompt string.
        """
        order = ["system", "example", "examples", "history", "document", "query"]
        sections: List[str] = []
        for key in order:
            if key in parts and parts[key].strip():
                sections.append(parts[key])
        # Include any remaining keys not in the standard order
        for key in parts:
            if key not in order and parts[key].strip():
                sections.append(parts[key])
        return "\n\n".join(sections)

    @staticmethod
    def _assess_quality_risk(savings_percent: float) -> str:
        """Assess quality risk based on savings percentage.

        Args:
            savings_percent: Token savings as a percentage.

        Returns:
            Risk level string.
        """
        if savings_percent < 15.0:
            return "none"
        elif savings_percent < 30.0:
            return "low"
        elif savings_percent < 50.0:
            return "medium"
        else:
            return "high"
