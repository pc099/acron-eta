"""
Few-shot example selector for Asahi token optimization.

When a prompt includes few-shot examples, selects only the most
relevant examples while maintaining diversity to avoid redundancy.
"""

import logging
from typing import Dict, List, Optional

import numpy as np

from src.embeddings.engine import EmbeddingEngine
from src.embeddings.similarity import SimilarityCalculator

logger = logging.getLogger(__name__)


class FewShotSelector:
    """Select the most relevant and diverse few-shot examples.

    Uses embedding similarity to score relevance, then applies a
    diversity penalty to prevent selecting near-duplicate examples.

    Args:
        embedding_engine: Engine for generating text embeddings.
    """

    def __init__(self, embedding_engine: EmbeddingEngine) -> None:
        self._embedding_engine = embedding_engine

        logger.info("FewShotSelector initialised")

    def select(
        self,
        query: str,
        examples: List[Dict[str, str]],
        max_examples: int = 3,
        diversity_weight: float = 0.2,
    ) -> List[Dict[str, str]]:
        """Select the best few-shot examples for a query.

        Algorithm:
            1. Embed the query.
            2. Embed each example's input.
            3. Score by cosine similarity to query.
            4. Greedily select, applying a diversity penalty for
               examples similar to already-selected ones.

        Args:
            query: The user's question.
            examples: List of example dicts with ``"input"`` and
                ``"output"`` keys.
            max_examples: Maximum number of examples to return.
            diversity_weight: How much to penalise similarity to
                already-selected examples (0.0 = no penalty,
                1.0 = heavy penalty).

        Returns:
            Selected examples in relevance order, up to ``max_examples``.
        """
        if not examples:
            return []

        if not query or not query.strip():
            return examples[:max_examples]

        if len(examples) <= max_examples:
            return list(examples)

        try:
            return self._select_with_embeddings(
                query, examples, max_examples, diversity_weight
            )
        except Exception as exc:
            logger.warning(
                "Embedding-based selection failed; returning first N examples",
                extra={"error": str(exc), "max_examples": max_examples},
            )
            return examples[:max_examples]

    def _select_with_embeddings(
        self,
        query: str,
        examples: List[Dict[str, str]],
        max_examples: int,
        diversity_weight: float,
    ) -> List[Dict[str, str]]:
        """Internal selection using embeddings.

        Args:
            query: User query.
            examples: All available examples.
            max_examples: How many to pick.
            diversity_weight: Diversity penalty factor.

        Returns:
            Selected examples.
        """
        # 1. Embed query
        query_vec = self._embedding_engine.embed_text(query)

        # 2. Embed each example's input
        example_inputs = [ex.get("input", "") for ex in examples]
        example_vecs = self._embedding_engine.embed_texts(example_inputs)

        # 3. Compute relevance scores
        relevance_scores = SimilarityCalculator.batch_similarity(
            query_vec, example_vecs
        )

        # 4. Greedy selection with diversity penalty
        selected_indices: List[int] = []
        selected_vecs: List[np.ndarray] = []
        remaining = list(range(len(examples)))

        for _ in range(min(max_examples, len(examples))):
            best_idx: Optional[int] = None
            best_score = -1.0

            for idx in remaining:
                score = relevance_scores[idx]

                # Apply diversity penalty
                if selected_vecs and diversity_weight > 0:
                    max_sim_to_selected = max(
                        SimilarityCalculator.cosine_similarity(
                            example_vecs[idx], sv
                        )
                        for sv in selected_vecs
                    )
                    score -= diversity_weight * max_sim_to_selected

                if score > best_score:
                    best_score = score
                    best_idx = idx

            if best_idx is not None:
                selected_indices.append(best_idx)
                selected_vecs.append(example_vecs[best_idx])
                remaining.remove(best_idx)

        logger.info(
            "Few-shot examples selected",
            extra={
                "total_available": len(examples),
                "selected": len(selected_indices),
                "max_examples": max_examples,
            },
        )

        return [examples[i] for i in selected_indices]
