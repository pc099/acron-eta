"""
Prompt compressor for Asahi token optimization.

Compresses prompt segments while preserving key information using
three strategies: extractive summarization, abstractive summarization,
and template compression.
"""

import logging
import re
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from src.models.registry import estimate_tokens

logger = logging.getLogger(__name__)


class CompressorConfig(BaseModel):
    """Configuration for PromptCompressor.

    Attributes:
        default_strategy: Which compression strategy to use by default.
        extractive_top_ratio: Fraction of sentences to keep in extractive mode.
        max_history_turns: Maximum chat turns to retain when compressing history.
        min_sentence_length: Ignore sentences shorter than this (in chars).
        template_patterns: Mapping of verbose patterns to shorter replacements.
    """

    default_strategy: Literal["extractive", "abstractive", "template"] = "extractive"
    extractive_top_ratio: float = Field(default=0.5, gt=0.0, le=1.0)
    max_history_turns: int = Field(default=5, ge=1)
    min_sentence_length: int = Field(default=10, ge=0)
    template_patterns: Dict[str, str] = Field(default_factory=lambda: {
        r"(?i)please\s+note\s+that\b": "Note:",
        r"(?i)it\s+is\s+important\s+to\s+note\s+that\b": "Note:",
        r"(?i)in\s+order\s+to\b": "to",
        r"(?i)as\s+a\s+matter\s+of\s+fact\b": "in fact",
        r"(?i)at\s+the\s+end\s+of\s+the\s+day\b": "ultimately",
        r"(?i)due\s+to\s+the\s+fact\s+that\b": "because",
        r"(?i)for\s+the\s+purpose\s+of\b": "for",
        r"(?i)in\s+the\s+event\s+that\b": "if",
        r"(?i)with\s+regard\s+to\b": "about",
        r"(?i)in\s+terms\s+of\b": "regarding",
        r"(?i)on\s+the\s+other\s+hand\b": "however",
        r"(?i)as\s+a\s+result\s+of\b": "because of",
        r"(?i)take\s+into\s+consideration\b": "consider",
        r"(?i)it\s+should\s+be\s+noted\s+that\b": "note:",
    })


class CompressionResult(BaseModel):
    """Result of a compression operation.

    Attributes:
        original_text: The input text before compression.
        compressed_text: The output text after compression.
        original_tokens: Estimated tokens in the original text.
        compressed_tokens: Estimated tokens in the compressed text.
        compression_ratio: Ratio of compressed to original tokens.
        strategy_used: Which strategy was applied.
    """

    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float = Field(ge=0.0, le=1.0)
    strategy_used: str


class PromptCompressor:
    """Compress prompt segments to reduce token count.

    Supports three strategies:

    * **extractive** -- Keeps the most important sentences based on
      keyword scoring.  Best for documents (50-70% compression).
    * **abstractive** -- Placeholder for LLM-based summarization.
      Returns a keyword-extracted summary for now (70-85% target).
    * **template** -- Replaces verbose patterns with shorter equivalents.
      Best for system prompts (60-80% compression).

    Args:
        config: Compressor configuration.
    """

    def __init__(self, config: Optional[CompressorConfig] = None) -> None:
        self._config = config or CompressorConfig()
        logger.info(
            "PromptCompressor initialised",
            extra={"default_strategy": self._config.default_strategy},
        )

    def compress(
        self,
        text: str,
        target_token_count: Optional[int] = None,
        strategy: Optional[Literal["extractive", "abstractive", "template"]] = None,
    ) -> CompressionResult:
        """Compress text using the specified strategy.

        Args:
            text: The text to compress.
            target_token_count: If set, aim for this token count.
            strategy: Compression strategy override. Uses config default
                if ``None``.

        Returns:
            :class:`CompressionResult` with original and compressed text.
        """
        if not text or not text.strip():
            return CompressionResult(
                original_text=text,
                compressed_text=text,
                original_tokens=0,
                compressed_tokens=0,
                compression_ratio=1.0,
                strategy_used=strategy or self._config.default_strategy,
            )

        strategy = strategy or self._config.default_strategy
        original_tokens = estimate_tokens(text)

        if strategy == "extractive":
            compressed = self._extractive_compress(text, target_token_count)
        elif strategy == "abstractive":
            compressed = self._abstractive_compress(text, target_token_count)
        elif strategy == "template":
            compressed = self._template_compress(text)
        else:
            compressed = text

        compressed_tokens = estimate_tokens(compressed)

        ratio = (
            compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        )

        logger.info(
            "Compression complete",
            extra={
                "strategy": strategy,
                "original_tokens": original_tokens,
                "compressed_tokens": compressed_tokens,
                "ratio": round(ratio, 3),
            },
        )

        return CompressionResult(
            original_text=text,
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=round(min(1.0, ratio), 3),
            strategy_used=strategy,
        )

    def compress_system_prompt(self, system_prompt: str) -> CompressionResult:
        """Compress a system prompt using template strategy.

        Args:
            system_prompt: The system prompt text.

        Returns:
            Compression result.
        """
        return self.compress(system_prompt, strategy="template")

    def compress_history(
        self,
        history: List[Dict[str, str]],
        max_turns: Optional[int] = None,
    ) -> CompressionResult:
        """Compress chat history by truncating and extracting key content.

        Args:
            history: List of turn dicts, each with ``"role"`` and
                ``"content"`` keys.
            max_turns: Maximum turns to keep. Uses config default if
                ``None``.

        Returns:
            Compression result.
        """
        max_turns = max_turns or self._config.max_history_turns

        if not history:
            return CompressionResult(
                original_text="",
                compressed_text="",
                original_tokens=0,
                compressed_tokens=0,
                compression_ratio=1.0,
                strategy_used="history_truncation",
            )

        # Build original text
        original_parts: List[str] = []
        for turn in history:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            original_parts.append(f"{role}: {content}")
        original_text = "\n".join(original_parts)

        # Keep only last N turns
        truncated = history[-max_turns:]
        compressed_parts: List[str] = []
        for turn in truncated:
            role = turn.get("role", "unknown")
            content = turn.get("content", "")
            # Further compress each turn with extractive
            if estimate_tokens(content) > 50:
                result = self._extractive_compress(content, target_tokens=30)
                compressed_parts.append(f"{role}: {result}")
            else:
                compressed_parts.append(f"{role}: {content}")
        compressed_text = "\n".join(compressed_parts)

        original_tokens = estimate_tokens(original_text)
        compressed_tokens = estimate_tokens(compressed_text)
        ratio = (
            compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        )

        return CompressionResult(
            original_text=original_text,
            compressed_text=compressed_text,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=round(min(1.0, ratio), 3),
            strategy_used="history_truncation",
        )

    def compress_document(self, document: str, query: str) -> CompressionResult:
        """Compress a document context relative to a query.

        Uses extractive compression, boosting sentences that contain
        query keywords.

        Args:
            document: The document text.
            query: The user query for relevance scoring.

        Returns:
            Compression result.
        """
        if not document or not document.strip():
            return CompressionResult(
                original_text=document,
                compressed_text=document,
                original_tokens=0,
                compressed_tokens=0,
                compression_ratio=1.0,
                strategy_used="extractive",
            )

        sentences = self._split_sentences(document)
        query_words = set(re.findall(r"[a-z0-9]+", query.lower()))

        # Score sentences by query keyword overlap
        scored: List[tuple] = []
        for idx, sentence in enumerate(sentences):
            words = set(re.findall(r"[a-z0-9]+", sentence.lower()))
            overlap = len(words & query_words) if query_words else 0
            # Position bonus: earlier sentences often more important
            position_bonus = max(0, 1.0 - (idx / max(len(sentences), 1)) * 0.3)
            score = overlap + position_bonus
            scored.append((score, idx, sentence))

        scored.sort(key=lambda x: x[0], reverse=True)

        # Keep top sentences
        keep_count = max(1, int(len(scored) * self._config.extractive_top_ratio))
        kept = sorted(scored[:keep_count], key=lambda x: x[1])  # restore order
        compressed = " ".join(s[2] for s in kept)

        original_tokens = estimate_tokens(document)
        compressed_tokens = estimate_tokens(compressed)
        ratio = (
            compressed_tokens / original_tokens if original_tokens > 0 else 1.0
        )

        return CompressionResult(
            original_text=document,
            compressed_text=compressed,
            original_tokens=original_tokens,
            compressed_tokens=compressed_tokens,
            compression_ratio=round(min(1.0, ratio), 3),
            strategy_used="extractive",
        )

    # ------------------------------------------------------------------
    # Strategy implementations
    # ------------------------------------------------------------------

    def _extractive_compress(
        self,
        text: str,
        target_tokens: Optional[int] = None,
    ) -> str:
        """Extractive compression: keep top-scoring sentences.

        Args:
            text: Input text.
            target_tokens: Optional target token count.

        Returns:
            Compressed text.
        """
        sentences = self._split_sentences(text)
        if len(sentences) <= 1:
            return text

        # Score each sentence by word importance
        scored = self._score_sentences(sentences)

        if target_tokens is not None:
            # Greedily add sentences by score until target is met
            kept: List[tuple] = []
            current_tokens = 0
            for score, idx, sentence in scored:
                s_tokens = estimate_tokens(sentence)
                if current_tokens + s_tokens <= target_tokens:
                    kept.append((score, idx, sentence))
                    current_tokens += s_tokens
            # Sort by original position
            kept.sort(key=lambda x: x[1])
            return " ".join(s[2] for s in kept) if kept else sentences[0]
        else:
            keep_count = max(1, int(len(scored) * self._config.extractive_top_ratio))
            kept_items = sorted(scored[:keep_count], key=lambda x: x[1])
            return " ".join(s[2] for s in kept_items)

    def _abstractive_compress(
        self,
        text: str,
        target_tokens: Optional[int] = None,
    ) -> str:
        """Abstractive compression placeholder.

        In production, this would call a small LLM to summarize.
        For now, applies aggressive extractive compression plus
        template compression.

        Args:
            text: Input text.
            target_tokens: Optional target token count.

        Returns:
            Compressed text.
        """
        # First apply template compression to remove verbosity
        templated = self._template_compress(text)
        # Then apply extractive with a tighter ratio
        sentences = self._split_sentences(templated)
        if len(sentences) <= 1:
            return templated

        scored = self._score_sentences(sentences)
        keep_ratio = 0.3  # more aggressive than extractive default

        if target_tokens is not None:
            kept: List[tuple] = []
            current_tokens = 0
            for score, idx, sentence in scored:
                s_tokens = estimate_tokens(sentence)
                if current_tokens + s_tokens <= target_tokens:
                    kept.append((score, idx, sentence))
                    current_tokens += s_tokens
            kept.sort(key=lambda x: x[1])
            return " ".join(s[2] for s in kept) if kept else sentences[0]
        else:
            keep_count = max(1, int(len(scored) * keep_ratio))
            kept_items = sorted(scored[:keep_count], key=lambda x: x[1])
            return " ".join(s[2] for s in kept_items)

    def _template_compress(self, text: str) -> str:
        """Template compression: replace verbose patterns.

        Args:
            text: Input text.

        Returns:
            Text with verbose patterns replaced.
        """
        result = text
        for pattern, replacement in self._config.template_patterns.items():
            result = re.sub(pattern, replacement, result)

        # Remove consecutive whitespace
        result = re.sub(r"\s+", " ", result).strip()
        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _score_sentences(self, sentences: List[str]) -> List[tuple]:
        """Score sentences by importance using word frequency.

        Args:
            sentences: List of sentences.

        Returns:
            List of (score, original_index, sentence) sorted by score
            descending.
        """
        # Build word frequency across all sentences
        word_freq: Dict[str, int] = {}
        for sentence in sentences:
            for word in re.findall(r"[a-z0-9]+", sentence.lower()):
                if len(word) > 2:
                    word_freq[word] = word_freq.get(word, 0) + 1

        scored: List[tuple] = []
        for idx, sentence in enumerate(sentences):
            words = re.findall(r"[a-z0-9]+", sentence.lower())
            score = sum(word_freq.get(w, 0) for w in words if len(w) > 2)
            # Normalise by sentence length to avoid favouring long sentences
            score = score / max(len(words), 1)
            scored.append((score, idx, sentence))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    @staticmethod
    def _split_sentences(text: str) -> List[str]:
        """Split text into sentences.

        Args:
            text: Input text.

        Returns:
            List of non-empty sentence strings.
        """
        # Split on period, exclamation, question mark followed by space or end
        raw = re.split(r"(?<=[.!?])\s+", text)
        return [s.strip() for s in raw if s.strip()]
