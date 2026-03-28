"""Heuristic classifiers for agent type and output type detection.

Fast pattern-based classification without requiring ML models.
Target: <5ms per classification.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# Agent type patterns
_CODE_PATTERNS = re.compile(
    r"\b(write|generate|create|debug|fix|refactor|implement|code|function|class|method)\s+(code|function|class|script|program|algorithm)",
    re.IGNORECASE,
)
_RAG_PATTERNS = re.compile(
    r"\b(search|find|lookup|retrieve|query|what does|tell me about|explain)\b.*\b(document|knowledge base|database|from|in the)\b",
    re.IGNORECASE,
)
_WORKFLOW_PATTERNS = re.compile(
    r"\b(workflow|pipeline|step|sequence|process|orchestrate|coordinate|schedule)\b",
    re.IGNORECASE,
)
_AUTONOMOUS_PATTERNS = re.compile(
    r"\b(autonomously|automatically|without intervention|continuously|monitor|decide|agent)\b",
    re.IGNORECASE,
)

# Output type patterns
_CODE_BLOCK_PATTERN = re.compile(r"```[\w]*\n", re.MULTILINE)
_JSON_PATTERN = re.compile(r"^\s*[\{\[]", re.MULTILINE)
_MARKDOWN_HEADERS = re.compile(r"^#+\s+", re.MULTILINE)
_NUMBERED_LIST = re.compile(r"^\d+\.\s+", re.MULTILINE)
_BULLET_LIST = re.compile(r"^[\*\-]\s+", re.MULTILINE)


def classify_agent_type(
    prompt: str,
    agent_name: Optional[str] = None,
    agent_metadata: Optional[dict] = None,
) -> str:
    """Classify agent type based on prompt, name, and metadata.

    Args:
        prompt: The user's prompt/query.
        agent_name: Optional agent name for additional context.
        agent_metadata: Optional agent metadata dict.

    Returns:
        One of: CHATBOT, RAG, CODING, WORKFLOW, AUTONOMOUS
    """
    # Check agent metadata first (if explicitly set)
    if agent_metadata and "agent_type" in agent_metadata:
        return agent_metadata["agent_type"].upper()

    # Check agent name patterns
    if agent_name:
        name_lower = agent_name.lower()
        if "code" in name_lower or "dev" in name_lower or "engineer" in name_lower:
            return "CODING"
        if "rag" in name_lower or "search" in name_lower or "knowledge" in name_lower:
            return "RAG"
        if "workflow" in name_lower or "pipeline" in name_lower:
            return "WORKFLOW"
        if "autonomous" in name_lower or "agent" in name_lower:
            return "AUTONOMOUS"

    # Pattern matching on prompt
    if _CODE_PATTERNS.search(prompt):
        return "CODING"
    if _RAG_PATTERNS.search(prompt):
        return "RAG"
    if _WORKFLOW_PATTERNS.search(prompt):
        return "WORKFLOW"
    if _AUTONOMOUS_PATTERNS.search(prompt):
        return "AUTONOMOUS"

    # Default: CHATBOT
    return "CHATBOT"


def classify_output_type(response: str) -> str:
    """Classify output type based on response structure.

    Args:
        response: The LLM's response text.

    Returns:
        One of: FACTUAL, CREATIVE, CODE, STRUCTURED, CONVERSATIONAL
    """
    # Check for code blocks
    if _CODE_BLOCK_PATTERN.search(response):
        return "CODE"

    # Check for JSON/structured data
    if _JSON_PATTERN.search(response):
        # Verify it's not just conversational JSON mention
        if response.count("{") > 2 or response.count("[") > 2:
            return "STRUCTURED"

    # Check for highly structured markdown
    headers = len(_MARKDOWN_HEADERS.findall(response))
    lists = len(_NUMBERED_LIST.findall(response)) + len(_BULLET_LIST.findall(response))

    if headers >= 3 or lists >= 5:
        return "STRUCTURED"

    # Check for factual vs creative
    # Factual indicators: specific numbers, dates, precise statements
    factual_score = 0
    creative_score = 0

    # Factual patterns
    if re.search(r"\d{4}", response):  # Years
        factual_score += 1
    if re.search(r"\d+%", response):  # Percentages
        factual_score += 1
    if re.search(r"\b(according to|based on|research shows|studies indicate)\b", response, re.IGNORECASE):
        factual_score += 2

    # Creative patterns
    if re.search(r"\b(imagine|story|creative|metaphor|analogy)\b", response, re.IGNORECASE):
        creative_score += 2
    if re.search(r'[\"\'].*[\"\']', response):  # Quotes/dialogue
        creative_score += 1

    if factual_score > creative_score and factual_score >= 2:
        return "FACTUAL"
    if creative_score > factual_score and creative_score >= 2:
        return "CREATIVE"

    # Default: CONVERSATIONAL
    return "CONVERSATIONAL"


def estimate_complexity(
    prompt: str,
    response: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Estimate query complexity (0.0-1.0) based on multiple signals.

    Args:
        prompt: User's prompt.
        response: LLM's response.
        input_tokens: Token count of input.
        output_tokens: Token count of output.

    Returns:
        Complexity score from 0.0 (trivial) to 1.0 (very complex).
    """
    complexity_score = 0.0

    # Token-based complexity (40% weight)
    # Short prompts (<50 tokens) = simple, long prompts (>500 tokens) = complex
    if input_tokens < 50:
        token_complexity = 0.1
    elif input_tokens < 150:
        token_complexity = 0.3
    elif input_tokens < 300:
        token_complexity = 0.5
    elif input_tokens < 500:
        token_complexity = 0.7
    else:
        token_complexity = 0.9

    complexity_score += token_complexity * 0.4

    # Output length complexity (20% weight)
    # Short responses (<100 tokens) = simple, long responses (>1000 tokens) = complex
    if output_tokens < 100:
        output_complexity = 0.2
    elif output_tokens < 300:
        output_complexity = 0.4
    elif output_tokens < 700:
        output_complexity = 0.6
    elif output_tokens < 1000:
        output_complexity = 0.8
    else:
        output_complexity = 1.0

    complexity_score += output_complexity * 0.2

    # Structural complexity (20% weight)
    structural_score = 0.0

    # Multi-step requests
    if re.search(r"\b(first|second|third|then|next|finally)\b", prompt, re.IGNORECASE):
        structural_score += 0.3

    # Code/technical requests
    if re.search(r"```|function|class|algorithm|implement", prompt + response, re.IGNORECASE):
        structural_score += 0.3

    # Multiple questions
    question_count = prompt.count("?")
    if question_count >= 3:
        structural_score += 0.4
    elif question_count == 2:
        structural_score += 0.2

    complexity_score += min(1.0, structural_score) * 0.2

    # Reasoning complexity (20% weight)
    reasoning_score = 0.0

    # Analytical/reasoning keywords
    if re.search(
        r"\b(analyze|compare|evaluate|explain why|reasoning|logic|prove|demonstrate)\b",
        prompt,
        re.IGNORECASE,
    ):
        reasoning_score += 0.5

    # Chain-of-thought indicators in response
    if re.search(r"\b(step \d+|first,|second,|therefore|thus|hence|because)\b", response, re.IGNORECASE):
        reasoning_score += 0.5

    complexity_score += min(1.0, reasoning_score) * 0.2

    # Clamp to [0.0, 1.0]
    return max(0.0, min(1.0, complexity_score))
