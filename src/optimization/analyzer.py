"""
Context analyzer for Asahi token optimization.

Scores each segment of a prompt by relevance to the user's query.
Identifies which parts of system prompt, document context, and chat
history actually contribute to answer quality, enabling safe removal
of low-relevance content.
"""

import hashlib
import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List, Literal, Optional

import numpy as np
from pydantic import BaseModel, Field

from src.embeddings.engine import EmbeddingEngine
from src.embeddings.similarity import SimilarityCalculator
from src.models.registry import estimate_tokens

logger = logging.getLogger(__name__)


class AnalyzerConfig(BaseModel):
    """Configuration for ContextAnalyzer.

    Attributes:
        min_relevance_threshold: Segments below this are candidates for removal.
        protected_categories: Never remove segments in these categories.
        max_history_turns: Keep only the last N turns of chat history.
        scoring_method: Algorithm used to score relevance.
        system_boost: Extra relevance added to system prompt segments.
    """

    min_relevance_threshold: float = Field(default=0.3, ge=0.0, le=1.0)
    protected_categories: List[str] = Field(default=["query"])
    max_history_turns: int = Field(default=5, ge=1)
    scoring_method: Literal["tfidf", "embedding", "keyword"] = "keyword"
    system_boost: float = Field(default=0.2, ge=0.0, le=1.0)


class SegmentScore(BaseModel):
    """A scored prompt segment.

    Attributes:
        segment_id: Unique identifier for this segment.
        text: The segment content.
        token_count: Estimated token count.
        relevance_score: 0.0 = irrelevant, 1.0 = critical.
        category: What kind of prompt part this segment belongs to.
    """

    segment_id: str
    text: str
    token_count: int
    relevance_score: float = Field(ge=0.0, le=1.0)
    category: Literal["system", "document", "history", "query", "example"]


class ContextAnalyzer:
    """Score prompt segments by relevance to the user query.

    Supports three scoring methods:

    * **keyword** -- simple keyword overlap (fast, no external deps).
    * **tfidf** -- TF-IDF weighted overlap (moderate accuracy).
    * **embedding** -- cosine similarity of dense vectors (best accuracy,
      requires :class:`EmbeddingEngine`).

    Args:
        config: Analyzer configuration.
        embedding_engine: Required when ``scoring_method="embedding"``.
    """

    def __init__(
        self,
        config: Optional[AnalyzerConfig] = None,
        embedding_engine: Optional[EmbeddingEngine] = None,
    ) -> None:
        self._config = config or AnalyzerConfig()
        self._embedding_engine = embedding_engine

        if self._config.scoring_method == "embedding" and embedding_engine is None:
            logger.warning(
                "Embedding scoring requested but no engine provided; "
                "falling back to keyword scoring"
            )
            self._config = self._config.model_copy(
                update={"scoring_method": "keyword"}
            )

        logger.info(
            "ContextAnalyzer initialised",
            extra={
                "scoring_method": self._config.scoring_method,
                "min_relevance": self._config.min_relevance_threshold,
            },
        )

    def analyze(
        self,
        prompt_parts: Dict[str, str],
        query: str,
    ) -> List[SegmentScore]:
        """Analyze prompt segments and score each by relevance.

        Args:
            prompt_parts: Mapping of category to text content.  Expected
                keys: ``"system"``, ``"document"``, ``"query"``,
                ``"history"``, ``"example"``.  Missing keys are ignored.
            query: The user's question used as the relevance anchor.

        Returns:
            List of :class:`SegmentScore` objects, one per non-empty
            segment.
        """
        segments: List[SegmentScore] = []

        for category, text in prompt_parts.items():
            if not text or not text.strip():
                continue

            # Truncate history to max_history_turns
            if category == "history":
                text = self._truncate_history(text)

            segment_id = self._make_segment_id(category, text)
            token_count = estimate_tokens(text)
            relevance = self._score_segment(text, query, category)

            segments.append(
                SegmentScore(
                    segment_id=segment_id,
                    text=text,
                    token_count=token_count,
                    relevance_score=relevance,
                    category=category,  # type: ignore[arg-type]
                )
            )

        logger.info(
            "Context analysis complete",
            extra={
                "segment_count": len(segments),
                "total_tokens": sum(s.token_count for s in segments),
            },
        )
        return segments

    def filter_by_relevance(
        self,
        segments: List[SegmentScore],
        min_relevance: Optional[float] = None,
    ) -> List[SegmentScore]:
        """Filter out segments below the relevance threshold.

        Protected categories are always retained regardless of their score.

        Args:
            segments: Scored segments from :meth:`analyze`.
            min_relevance: Override for the config threshold.

        Returns:
            Filtered list of segments.
        """
        threshold = (
            min_relevance
            if min_relevance is not None
            else self._config.min_relevance_threshold
        )

        result: List[SegmentScore] = []
        for seg in segments:
            if seg.category in self._config.protected_categories:
                result.append(seg)
            elif seg.relevance_score >= threshold:
                result.append(seg)
            else:
                logger.debug(
                    "Segment filtered out",
                    extra={
                        "segment_id": seg.segment_id,
                        "category": seg.category,
                        "relevance": seg.relevance_score,
                        "threshold": threshold,
                    },
                )

        return result

    def estimate_token_savings(
        self,
        original_segments: List[SegmentScore],
        filtered_segments: List[SegmentScore],
    ) -> Dict[str, Any]:
        """Calculate token savings from filtering.

        Args:
            original_segments: All scored segments before filtering.
            filtered_segments: Segments retained after filtering.

        Returns:
            Dict with ``original_tokens``, ``filtered_tokens``,
            ``tokens_saved``, ``savings_percent``, and per-category
            breakdown in ``by_category``.
        """
        original_tokens = sum(s.token_count for s in original_segments)
        filtered_tokens = sum(s.token_count for s in filtered_segments)
        tokens_saved = original_tokens - filtered_tokens
        savings_pct = (
            round((tokens_saved / original_tokens) * 100, 1)
            if original_tokens > 0
            else 0.0
        )

        # Per-category breakdown
        orig_by_cat: Dict[str, int] = {}
        filt_by_cat: Dict[str, int] = {}
        for seg in original_segments:
            orig_by_cat[seg.category] = (
                orig_by_cat.get(seg.category, 0) + seg.token_count
            )
        for seg in filtered_segments:
            filt_by_cat[seg.category] = (
                filt_by_cat.get(seg.category, 0) + seg.token_count
            )

        by_category: Dict[str, Dict[str, int]] = {}
        for cat in orig_by_cat:
            orig = orig_by_cat.get(cat, 0)
            filt = filt_by_cat.get(cat, 0)
            by_category[cat] = {
                "original": orig,
                "filtered": filt,
                "saved": orig - filt,
            }

        return {
            "original_tokens": original_tokens,
            "filtered_tokens": filtered_tokens,
            "tokens_saved": tokens_saved,
            "savings_percent": savings_pct,
            "by_category": by_category,
        }

    # ------------------------------------------------------------------
    # Scoring methods
    # ------------------------------------------------------------------

    def _score_segment(self, text: str, query: str, category: str) -> float:
        """Score a segment's relevance to the query.

        Args:
            text: The segment content.
            query: The user's question.
            category: The segment category.

        Returns:
            Relevance score in [0.0, 1.0].
        """
        # Protected categories always get 1.0
        if category in self._config.protected_categories:
            return 1.0

        if self._config.scoring_method == "embedding":
            score = self._score_embedding(text, query)
        elif self._config.scoring_method == "tfidf":
            score = self._score_tfidf(text, query)
        else:
            score = self._score_keyword(text, query)

        # Apply system prompt boost
        if category == "system":
            score = min(1.0, score + self._config.system_boost)

        return round(score, 3)

    def _score_keyword(self, text: str, query: str) -> float:
        """Keyword overlap scoring.

        Args:
            text: Segment text.
            query: User query.

        Returns:
            Overlap ratio in [0.0, 1.0].
        """
        query_words = set(self._tokenize(query))
        text_words = set(self._tokenize(text))

        if not query_words:
            return 0.0

        overlap = query_words & text_words
        return len(overlap) / len(query_words)

    def _score_tfidf(self, text: str, query: str) -> float:
        """TF-IDF weighted scoring.

        Computes a simplified TF-IDF score measuring how well the
        segment matches the query terms, weighted by inverse document
        frequency approximation.

        Args:
            text: Segment text.
            query: User query.

        Returns:
            Normalised score in [0.0, 1.0].
        """
        query_tokens = self._tokenize(query)
        text_tokens = self._tokenize(text)

        if not query_tokens or not text_tokens:
            return 0.0

        text_counter = Counter(text_tokens)
        total_text_tokens = len(text_tokens)

        score = 0.0
        for token in query_tokens:
            tf = text_counter.get(token, 0) / total_text_tokens
            # Simplified IDF: penalise very common short words
            idf = math.log(1 + 1 / (1 + text_counter.get(token, 0)))
            score += tf * idf

        # Normalise to [0, 1]
        max_possible = len(query_tokens) * math.log(2)
        if max_possible > 0:
            score = min(1.0, score / max_possible)

        return score

    def _score_embedding(self, text: str, query: str) -> float:
        """Embedding-based cosine similarity scoring.

        Args:
            text: Segment text.
            query: User query.

        Returns:
            Cosine similarity in [0.0, 1.0].
        """
        if self._embedding_engine is None:
            return self._score_keyword(text, query)

        try:
            query_vec = self._embedding_engine.embed_text(query)
            text_vec = self._embedding_engine.embed_text(text)
            similarity = SimilarityCalculator.cosine_similarity(query_vec, text_vec)
            # Clamp to positive range for relevance
            return max(0.0, similarity)
        except Exception as exc:
            logger.warning(
                "Embedding scoring failed; falling back to keyword",
                extra={"error": str(exc)},
            )
            return self._score_keyword(text, query)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple word tokenization with lowering and stop-word removal.

        Args:
            text: Input text.

        Returns:
            List of cleaned tokens.
        """
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "being", "have", "has", "had", "do", "does", "did", "will",
            "would", "could", "should", "may", "might", "shall", "can",
            "to", "of", "in", "for", "on", "with", "at", "by", "from",
            "as", "into", "through", "during", "before", "after", "and",
            "but", "or", "nor", "not", "so", "yet", "both", "either",
            "neither", "each", "every", "all", "any", "few", "more",
            "most", "other", "some", "such", "no", "only", "own", "same",
            "than", "too", "very", "just", "because", "if", "when",
            "where", "how", "what", "which", "who", "whom", "this",
            "that", "these", "those", "i", "me", "my", "we", "our",
            "you", "your", "he", "him", "his", "she", "her", "it", "its",
            "they", "them", "their",
        }
        words = re.findall(r"[a-z0-9]+", text.lower())
        return [w for w in words if w not in stop_words and len(w) > 1]

    def _truncate_history(self, history_text: str) -> str:
        """Keep only the last N turns of chat history.

        Turns are separated by double newlines.

        Args:
            history_text: Full chat history string.

        Returns:
            Truncated history with at most ``max_history_turns`` turns.
        """
        turns = [t.strip() for t in history_text.split("\n\n") if t.strip()]
        max_turns = self._config.max_history_turns
        if len(turns) > max_turns:
            turns = turns[-max_turns:]
        return "\n\n".join(turns)

    @staticmethod
    def _make_segment_id(category: str, text: str) -> str:
        """Generate a deterministic segment ID.

        Args:
            category: Segment category.
            text: Segment content.

        Returns:
            ID string like ``"system-a1b2c3d4"``.
        """
        digest = hashlib.md5(text.encode()).hexdigest()[:8]
        return f"{category}-{digest}"
