# Phase 4: Token Optimization -- Component Specification

> **Status**: PLANNED  
> **Timeline**: 12 weeks (can run parallel with Phase 3)  
> **Additional cost savings**: +15% (total 95-97%)  
> **Research basis**: LLMLingua-2 (arxiv 2403.12968)  

---

## 1. Objective

Analyze prompts to remove unnecessary tokens, compress context, and select optimal few-shot examples.  Reduce token count by 20-30% without quality loss.

---

## 2. Component 1: ContextAnalyzer

### 2.1 Purpose

Score each segment of a prompt by relevance to the user's question.  Identify which parts of system prompt, document context, and chat history actually contribute to answer quality.

### 2.2 File

`src/phase4/context_analyzer.py`

### 2.3 Public Interface

```python
class SegmentScore(BaseModel):
    segment_id: str
    text: str
    token_count: int
    relevance_score: float  # 0.0 = irrelevant, 1.0 = critical
    category: Literal["system", "document", "history", "query", "example"]

class ContextAnalyzer:
    def __init__(self, config: AnalyzerConfig) -> None: ...
    
    def analyze(
        self,
        prompt_parts: Dict[str, str],  # {"system": "...", "document": "...", "query": "...", "history": "..."}
        query: str
    ) -> List[SegmentScore]: ...
    
    def filter_by_relevance(
        self,
        segments: List[SegmentScore],
        min_relevance: float = 0.3
    ) -> List[SegmentScore]: ...
    
    def estimate_token_savings(
        self,
        original_segments: List[SegmentScore],
        filtered_segments: List[SegmentScore]
    ) -> Dict[str, Any]: ...
```

#### `AnalyzerConfig` (Pydantic BaseModel)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `min_relevance_threshold` | `float` | `0.3` | Segments below this are candidates for removal |
| `protected_categories` | `List[str]` | `["query"]` | Never remove these |
| `max_history_turns` | `int` | `5` | Keep only last N turns of chat history |
| `scoring_method` | `Literal["tfidf","embedding","keyword"]` | `"embedding"` | How to score relevance |

### 2.4 Scoring Method

For `embedding` scoring:
```
1. Embed the user query
2. Embed each segment
3. relevance = cosine_similarity(query_embedding, segment_embedding)
4. Boost system prompt segments by 0.2 (they set behaviour)
5. Protected categories always get score 1.0
```

### 2.5 Testing Requirements

- 10+ tests: segment scoring, filtering, irrelevant document removal, history truncation, protected category preservation, token savings calculation.

---

## 3. Component 2: PromptCompressor

### 3.1 Purpose

Compress prompt segments while preserving key information.  Multiple strategies: extractive summarization, redundancy removal, and template compression.

### 3.2 File

`src/phase4/prompt_compressor.py`

### 3.3 Public Interface

```python
class CompressionResult(BaseModel):
    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    strategy_used: str

class PromptCompressor:
    def __init__(self, config: CompressorConfig) -> None: ...
    
    def compress(
        self,
        text: str,
        target_token_count: Optional[int] = None,
        strategy: Literal["extractive", "abstractive", "template"] = "extractive"
    ) -> CompressionResult: ...
    
    def compress_system_prompt(self, system_prompt: str) -> CompressionResult: ...
    def compress_history(self, history: List[Dict], max_turns: int = 5) -> CompressionResult: ...
    def compress_document(self, document: str, query: str) -> CompressionResult: ...
```

### 3.4 Compression Strategies

| Strategy | Method | Best For | Compression Ratio |
|----------|--------|----------|-------------------|
| Extractive | Keep key sentences; remove filler | Documents | 50-70% |
| Abstractive | Summarize using small LLM | Long histories | 70-85% |
| Template | Replace repeated patterns with shorter versions | System prompts | 60-80% |

### 3.5 Testing Requirements

- 10+ tests: each strategy, target token count respect, quality preservation (compare LLM output with/without compression), edge cases (already short text, empty input).

---

## 4. Component 3: FewShotSelector

### 4.1 Purpose

When a prompt includes few-shot examples, select only the most relevant examples instead of including all of them.

### 4.2 File

`src/phase4/few_shot_selector.py`

### 4.3 Public Interface

```python
class FewShotSelector:
    def __init__(self, embedding_engine: EmbeddingEngine) -> None: ...
    
    def select(
        self,
        query: str,
        examples: List[Dict[str, str]],  # [{"input": "...", "output": "..."}]
        max_examples: int = 3,
        diversity_weight: float = 0.2
    ) -> List[Dict[str, str]]: ...
```

### 4.4 Selection Algorithm

```
1. Embed the query
2. Embed each example's input
3. Score each example: relevance = cosine_similarity(query, example)
4. Apply diversity penalty: reduce score for examples similar to already-selected ones
5. Greedily select top max_examples by adjusted score
```

### 4.5 Testing Requirements

- 8+ tests: relevance-based selection, diversity prevents duplicate-ish examples, max_examples respected, empty examples list.

---

## 5. Component 4: TokenOptimizer (Orchestrator)

### 5.1 Purpose

Combine context analysis, compression, and few-shot selection into a single optimization pipeline.

### 5.2 File

`src/phase4/token_optimizer.py`

### 5.3 Public Interface

```python
class OptimizationResult(BaseModel):
    original_prompt: str
    optimized_prompt: str
    original_tokens: int
    optimized_tokens: int
    tokens_saved: int
    savings_percent: float
    strategies_applied: List[str]
    quality_risk: Literal["none", "low", "medium", "high"]

class TokenOptimizer:
    def __init__(
        self,
        analyzer: ContextAnalyzer,
        compressor: PromptCompressor,
        few_shot_selector: FewShotSelector,
        config: OptimizerConfig
    ) -> None: ...
    
    def optimize(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict]] = None,
        examples: Optional[List[Dict]] = None,
        task_type: str = "general",
        quality_preference: str = "medium"
    ) -> OptimizationResult: ...
```

### 5.4 Pipeline

```
1. Parse prompt into segments (system, document, query, history, examples)
2. Analyze relevance of each segment
3. Remove segments below relevance threshold
4. Compress remaining segments (strategy based on segment category)
5. Select best few-shot examples if applicable
6. Reassemble optimized prompt
7. Calculate savings and quality risk
```

### 5.5 Quality Risk Assessment

| Savings % | Risk Level | Action |
|-----------|-----------|--------|
| < 15% | none | Safe to apply |
| 15-30% | low | Apply; monitor quality |
| 30-50% | medium | Apply only for non-critical tasks |
| > 50% | high | Flag for review; may skip optimization |

### 5.6 Testing Requirements

- 10+ tests: full pipeline, each strategy combination, quality risk assessment, skip optimization when risk too high, token counting accuracy.

---

## 6. Performance Targets

| Metric | Target |
|--------|--------|
| Token reduction | 20-30% average |
| Quality maintenance | >= 4.0/5.0 |
| Optimization overhead | < 50 ms (excluding any LLM calls for abstractive compression) |
| Cost savings | +15% incremental |

### Example

```
Original Prompt:
  System prompt:      500 tokens
  Document context:  2000 tokens (90% irrelevant)
  User question:      100 tokens
  Chat history:       800 tokens (50% relevant)
  Total:             3400 tokens -> Cost $0.050

After Optimization:
  Compressed system:  100 tokens
  Relevant docs:      150 tokens
  User question:      100 tokens (protected)
  Filtered history:   300 tokens
  Total:              650 tokens -> Cost $0.009 (82% cheaper!)
```

---

## 7. Acceptance Criteria

- [ ] ContextAnalyzer correctly scores segment relevance
- [ ] PromptCompressor achieves 50%+ compression on long documents
- [ ] FewShotSelector picks most relevant examples
- [ ] TokenOptimizer pipeline produces 20-30% token reduction on benchmark
- [ ] Quality score does not drop below 4.0 on compressed prompts
- [ ] Quality risk correctly flagged for aggressive compression
- [ ] 40+ unit tests with >90% coverage
- [ ] No hardcoded thresholds or token limits
