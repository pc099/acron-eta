# Phase 2: Semantic Caching and Advanced Routing -- Component Specification

> **Status**: IN PROGRESS  
> **Timeline**: 12 weeks  
> **Cost savings target**: 85-92%  
> **Cache hit rate target**: 75-90% (3-tier)  
> **Quality floor**: 4.0 / 5.0  
> **Latency overhead budget**: < 20 ms for cache operations  
> **Research basis**: arxiv 2505.11271, arxiv 2508.07675  

---

## 1. Phase 2 Overview

Phase 2 transforms Asahi from a simple router+cache into a production semantic caching platform.  It adds:

1. **Three-tier caching** -- exact match, semantic similarity, intermediate result reuse.
2. **Three routing modes** -- AUTOPILOT, GUIDED, EXPLICIT.
3. **Contextual Retrieval** (Phase 2+) -- Anthropic-inspired context enrichment before embedding.

These are delivered by 12 new components described below.

---

## 2. Component 1: EmbeddingEngine

### 2.1 Purpose

Generate dense vector embeddings for text queries and cached items.  This is the foundation for all semantic matching in Tier 2 and Tier 3 caching.

### 2.2 File

`src/phase2/embedding_engine.py`

### 2.3 Public Interface

```python
class EmbeddingEngine:
    def __init__(self, config: EmbeddingConfig) -> None: ...
    def embed_text(self, text: str) -> np.ndarray: ...
    def embed_texts(self, texts: List[str]) -> List[np.ndarray]: ...
    def dimension(self) -> int: ...
```

#### `EmbeddingConfig` (Pydantic BaseModel)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `provider` | `Literal["cohere","openai","ollama"]` | `"cohere"` | Which embedding API to use |
| `model_name` | `str` | `"embed-english-v3.0"` | Specific model identifier |
| `api_key_env` | `str` | `"COHERE_API_KEY"` | Env var holding the key |
| `dimension` | `int` | `1024` | Expected vector dimension |
| `batch_size` | `int` | `96` | Max texts per API call |
| `timeout_seconds` | `int` | `30` | API call timeout |
| `max_retries` | `int` | `3` | Retry count on transient failures |

### 2.4 Behaviour

- `embed_text`: embed a single string; return a numpy array of shape `(dimension,)`.
- `embed_texts`: batch embed; split into chunks of `batch_size`, call API, concatenate results.  Return in same order as input.
- Normalize all vectors to unit length (L2 norm = 1) so that dot product equals cosine similarity.
- Cache the API client instance; do not create a new client per call.

### 2.5 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Empty string input | Raise `ValueError("Text must not be empty")` |
| API timeout | Retry up to `max_retries` with exponential backoff; then raise `EmbeddingError` |
| API rate limit (429) | Wait `retry-after` header duration; retry |
| Invalid API key | Raise `ConfigurationError` on init |
| Response dimension mismatch | Raise `EmbeddingError` with expected vs actual dimensions |

### 2.6 Performance Targets

| Metric | Target |
|--------|--------|
| Single text embed (API round trip) | < 100 ms |
| Batch of 10 texts | < 200 ms |
| Batch of 96 texts | < 500 ms |

### 2.7 Testing Requirements

- 12+ unit tests, 100% line coverage.
- Mock the API client for deterministic testing.
- Test: single text, batch, empty input rejection, timeout retry, dimension validation.
- Performance test: 10 texts in < 100 ms (with mocked API).

---

## 3. Component 2: SimilarityCalculator

### 3.1 Purpose

Compute cosine similarity between two embedding vectors.  Provide utility methods for batch similarity and threshold checking.

### 3.2 File

`src/phase2/similarity.py`

### 3.3 Public Interface

```python
class SimilarityCalculator:
    @staticmethod
    def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float: ...
    
    @staticmethod
    def batch_similarity(query: np.ndarray, candidates: List[np.ndarray]) -> List[float]: ...
    
    @staticmethod
    def above_threshold(similarity: float, threshold: float) -> bool: ...
```

### 3.4 Behaviour

- Vectors must be same length; raise `ValueError` if not.
- Return value in range `[-1.0, 1.0]`.  In practice, normalized embeddings produce `[0.0, 1.0]`.
- `batch_similarity`: vectorised computation using numpy for performance.

### 3.5 Testing Requirements

- 8+ tests: identical vectors (= 1.0), orthogonal (= 0.0), opposite (= -1.0), mismatched dimensions, batch correctness.

---

## 4. Component 3: MismatchCostCalculator

### 4.1 Purpose

Decide whether using a cached response (with some semantic distance) is cheaper than recomputing.  This is the economic engine behind Tier 2 cache decisions.

### 4.2 File

`src/phase2/mismatch_cost.py`

### 4.3 Public Interface

```python
class MismatchCostCalculator:
    def __init__(self, config: MismatchConfig) -> None: ...
    
    def calculate_mismatch_cost(
        self,
        similarity: float,
        task_type: str,
        model_cost: float
    ) -> float: ...
    
    def should_use_cache(
        self,
        similarity: float,
        task_type: str,
        recompute_cost: float
    ) -> Tuple[bool, str]: ...
```

#### `MismatchConfig` (Pydantic BaseModel)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `quality_penalty_weight` | `float` | `2.0` | Multiplier for quality risk |
| `task_weights` | `Dict[str, float]` | see below | Per-task sensitivity |

Default `task_weights`:
```yaml
faq: 1.0           # Low sensitivity -- reuse aggressively
summarization: 1.5  # Medium
reasoning: 2.5      # High sensitivity -- conservative
coding: 3.0         # Very high -- code must be correct
legal: 4.0          # Critical -- almost never reuse imperfect match
```

### 4.4 Algorithm

```
mismatch_cost = (1 - similarity) * quality_penalty_weight * task_weight * model_cost

should_use_cache:
    if mismatch_cost < recompute_cost:
        return (True, "Mismatch cost ${mc} < recompute cost ${rc}")
    else:
        return (False, "Recomputing: mismatch risk too high")
```

### 4.5 Testing Requirements

- 10+ tests: high similarity (should cache), low similarity (should recompute), boundary cases, different task types, edge case similarity=1.0 (zero mismatch cost).

---

## 5. Component 4: AdaptiveThresholdTuner

### 5.1 Purpose

Select the optimal similarity threshold per task type and cost sensitivity level.  Thresholds are configurable and can be tuned based on observed data over time.

### 5.2 File

`src/phase2/threshold_tuner.py`

### 5.3 Public Interface

```python
class AdaptiveThresholdTuner:
    def __init__(self, config: ThresholdConfig) -> None: ...
    
    def get_threshold(
        self,
        task_type: str,
        cost_sensitivity: Literal["high", "medium", "low"]
    ) -> float: ...
    
    def update_threshold(
        self,
        task_type: str,
        cost_sensitivity: str,
        new_threshold: float
    ) -> None: ...
```

### 5.4 Default Thresholds

| Task Type | High Sensitivity | Medium | Low |
|-----------|-----------------|--------|-----|
| faq | 0.70 | 0.80 | 0.90 |
| summarization | 0.80 | 0.85 | 0.92 |
| reasoning | 0.85 | 0.90 | 0.95 |
| coding | 0.90 | 0.93 | 0.97 |
| legal | 0.88 | 0.92 | 0.96 |
| default | 0.80 | 0.85 | 0.92 |

### 5.5 Testing Requirements

- 8+ tests: known task types, unknown task type falls back to default, threshold update persists, boundary values.

---

## 6. Component 5: VectorDatabase

### 6.1 Purpose

Store, query, and manage embedding vectors.  Provides a backend-agnostic interface with implementations for Pinecone (production) and an in-memory store (development/testing).

### 6.2 File

`src/phase2/vector_db.py`

### 6.3 Public Interface

```python
class VectorDBEntry(BaseModel):
    vector_id: str
    embedding: List[float]
    metadata: Dict[str, Any]

class VectorSearchResult(BaseModel):
    vector_id: str
    score: float            # cosine similarity 0-1
    metadata: Dict[str, Any]

class VectorDatabase(Protocol):
    def upsert(self, entries: List[VectorDBEntry]) -> int: ...
    def query(self, embedding: List[float], top_k: int = 5, filter: Optional[Dict] = None) -> List[VectorSearchResult]: ...
    def delete(self, vector_ids: List[str]) -> int: ...
    def count(self) -> int: ...

class InMemoryVectorDB:
    """Development/test implementation using brute-force cosine search."""

class PineconeVectorDB:
    """Production implementation backed by Pinecone serverless."""
    def __init__(self, api_key_env: str, index_name: str, dimension: int): ...
```

### 6.4 Pinecone Configuration

| Parameter | Value |
|-----------|-------|
| Index name | `asahi-cache` |
| Metric | `cosine` |
| Dimension | `1024` (matches Cohere embed-english-v3.0) |
| Cloud | `aws`, region `us-east-1` |
| Pod type | `serverless` (scales to zero) |

### 6.5 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Pinecone API down | Retry 3x; fall back to skip Tier 2 (degrade gracefully) |
| Vector dimension mismatch | Raise `VectorDBError` |
| Index not found | Create index on first upsert; log warning |

### 6.6 Performance Targets

| Operation | Target |
|-----------|--------|
| Single upsert | < 50 ms |
| Query top-5 | < 30 ms |
| Batch upsert (100 vectors) | < 500 ms |

### 6.7 Testing Requirements

- 10+ tests using `InMemoryVectorDB`: upsert, query, delete, count, filter, empty DB query.
- Integration test with Pinecone (gated by env var `RUN_INTEGRATION_TESTS=true`).

---

## 7. Component 6: SemanticCache (Tier 2 Orchestrator)

### 7.1 Purpose

Orchestrate Tier 2 caching: embed the query, search the vector DB for similar cached queries, evaluate mismatch cost, and return cached response or signal a miss.

### 7.2 File

`src/phase2/semantic_cache.py`

### 7.3 Public Interface

```python
class SemanticCacheResult(BaseModel):
    hit: bool
    response: Optional[str]
    similarity: Optional[float]
    cached_query: Optional[str]
    reason: str

class SemanticCache:
    def __init__(
        self,
        embedding_engine: EmbeddingEngine,
        vector_db: VectorDatabase,
        similarity_calc: SimilarityCalculator,
        mismatch_calc: MismatchCostCalculator,
        threshold_tuner: AdaptiveThresholdTuner
    ) -> None: ...
    
    def get(
        self,
        query: str,
        task_type: str = "general",
        cost_sensitivity: str = "medium",
        recompute_cost: float = 0.01
    ) -> SemanticCacheResult: ...
    
    def set(
        self,
        query: str,
        response: str,
        model: str,
        cost: float,
        task_type: str = "general"
    ) -> None: ...
    
    def invalidate(self, query: str) -> bool: ...
    
    def stats(self) -> Dict[str, Any]: ...
```

### 7.4 `get` Algorithm

```
1. Embed the query
2. Search vector DB for top-5 similar entries
3. For each result (highest similarity first):
   a. Get threshold from tuner for (task_type, cost_sensitivity)
   b. If result.score >= threshold:
      c. Calculate mismatch cost
      d. If should_use_cache:
         return SemanticCacheResult(hit=True, response=..., similarity=result.score)
4. Return SemanticCacheResult(hit=False, reason="No sufficiently similar cached query")
```

### 7.5 `set` Flow

```
1. Embed the query
2. Upsert to vector DB with metadata:
   {query, response, model, cost, task_type, created_at, expires_at}
3. Log: "Cached query for task_type={task_type}"
```

### 7.6 Testing Requirements

- 15+ tests: hit above threshold, miss below threshold, mismatch cost rejection, empty DB, multiple candidates with varying similarity, invalidation, stats tracking.
- Performance: `get` completes in < 50 ms with 1000 entries in `InMemoryVectorDB`.

---

## 8. Component 7: WorkflowDecomposer

### 8.1 Purpose

Break a complex request into discrete steps, each of which can be cached independently.  This enables Tier 3 intermediate result reuse.

### 8.2 File

`src/phase2/workflow_decomposer.py`

### 8.3 Public Interface

```python
class WorkflowStep(BaseModel):
    step_id: str
    step_type: str        # "summarize", "extract", "classify", "answer"
    intent: str           # specific intent within the type
    document_id: Optional[str]
    input_text: str
    cache_key: str        # composite key: "{doc_id}:{step_type}:{intent}"
    result: Optional[str] # filled after execution or cache hit

class WorkflowDecomposer:
    def __init__(self, config: WorkflowConfig) -> None: ...
    
    def decompose(
        self,
        prompt: str,
        document_id: Optional[str] = None,
        task_type: Optional[str] = None
    ) -> List[WorkflowStep]: ...
    
    def extract_intent(self, text: str) -> str: ...
    
    def extract_document_sections(self, text: str) -> List[str]: ...
```

### 8.4 Decomposition Rules

| Pattern | Steps Generated |
|---------|----------------|
| Single question, no document | 1 step: direct answer |
| Question with document reference | 2 steps: summarise relevant section, answer from summary |
| Multi-part question | N steps: one per sub-question |
| Comparison question | 3 steps: summarise A, summarise B, compare summaries |

### 8.5 Testing Requirements

- 10+ tests: single-step queries, multi-step decomposition, document-referenced queries, intent extraction accuracy.

---

## 9. Component 8: IntermediateCache (Tier 3 Orchestrator)

### 9.1 Purpose

Cache and retrieve intermediate results (e.g., section summaries) identified by composite keys `(document_id, step_type, intent)`.  This allows different queries that need the same intermediate work to skip redundant computation.

### 9.2 File

`src/phase2/intermediate_cache.py`

### 9.3 Public Interface

```python
class IntermediateCacheResult(BaseModel):
    hit: bool
    result: Optional[str]
    step_id: str
    cache_key: str

class IntermediateCache:
    def __init__(self, ttl_seconds: int = 86400) -> None: ...
    
    def get(self, cache_key: str) -> Optional[str]: ...
    def set(self, cache_key: str, result: str, metadata: Dict[str, Any]) -> None: ...
    def invalidate(self, cache_key: str) -> bool: ...
    def invalidate_by_document(self, document_id: str) -> int: ...
    def stats(self) -> Dict[str, Any]: ...
    
    def execute_workflow(
        self,
        steps: List[WorkflowStep],
        executor: Callable[[WorkflowStep], str]
    ) -> List[WorkflowStep]: ...
```

### 9.4 `execute_workflow` Algorithm

```
for step in steps:
    cached = self.get(step.cache_key)
    if cached:
        step.result = cached
        log("Tier 3 cache hit for step {step.step_id}")
    else:
        step.result = executor(step)
        self.set(step.cache_key, step.result, {...})
        log("Tier 3 cache miss for step {step.step_id}; executed and cached")
return steps
```

### 9.5 Testing Requirements

- 10+ tests: hit, miss, workflow execution with mixed hits/misses, TTL expiry, document-level invalidation.

---

## 10. Component 9: TaskTypeDetector

### 10.1 Purpose

Automatically detect the task type (summarization, reasoning, faq, coding, etc.) from the user's prompt.  Used by AUTOPILOT routing mode and threshold tuning.

### 10.2 File

`src/phase2/task_detector.py`

### 10.3 Public Interface

```python
class TaskDetection(BaseModel):
    task_type: str
    confidence: float   # 0.0 - 1.0
    intent: str

class TaskTypeDetector:
    def __init__(self) -> None: ...
    def detect(self, prompt: str) -> TaskDetection: ...
```

### 10.4 Detection Strategy (MVP -- keyword/pattern based)

| Pattern | Detected Type |
|---------|---------------|
| "summarize", "summary", "tldr" | `summarization` |
| "why", "explain", "reason", "analyze" | `reasoning` |
| "how do I", "what is", "help with" | `faq` |
| "write code", "implement", "function", "class" | `coding` |
| "translate", "convert to" | `translation` |
| "classify", "categorize" | `classification` |
| Default fallback | `general` |

Confidence is based on number of pattern matches; higher = more certain.

### 10.5 Testing Requirements

- 10+ tests: each task type with representative prompts, ambiguous prompts, empty prompt handling.

---

## 11. Component 10: ConstraintInterpreter

### 11.1 Purpose

Convert human-friendly user preferences (e.g., `quality_preference="high"`) into concrete numeric constraints for the router.

### 11.2 File

`src/phase2/constraint_interpreter.py`

### 11.3 Public Interface

```python
class ConstraintInterpreter:
    def interpret(
        self,
        quality_preference: Optional[str],  # low, medium, high, max
        latency_preference: Optional[str],  # slow, normal, fast, instant
        task_type: str
    ) -> RoutingConstraints: ...
```

### 11.4 Mapping Tables

**Quality preference -> threshold:**

| Preference | Threshold |
|-----------|-----------|
| low | 3.0 |
| medium | 3.5 |
| high | 4.0 |
| max | 4.5 |

**Latency preference -> budget (ms):**

| Preference | Budget |
|-----------|--------|
| slow | 2000 |
| normal | 500 |
| fast | 300 |
| instant | 150 |

**Task-type overrides** (applied after user preference):

| Task Type | Min Quality | Max Latency |
|-----------|------------|-------------|
| coding | max(user, 4.0) | min(user, 500) |
| reasoning | max(user, 4.0) | min(user, 500) |
| legal | max(user, 4.2) | min(user, 2000) |

### 11.5 Testing Requirements

- 8+ tests: all preference values, task-type overrides, null preferences (use defaults).

---

## 12. Component 11: AdvancedRouter (3 Modes)

### 12.1 Purpose

Extends the Phase 1 router with three distinct routing modes to serve different user personas.

### 12.2 File

`src/phase2/advanced_router.py`

### 12.3 Public Interface

```python
class AdvancedRoutingDecision(BaseModel):
    model_name: str
    mode: Literal["autopilot", "guided", "explicit"]
    score: float
    reason: str
    alternatives: List[ModelAlternative]  # populated in EXPLICIT mode
    task_type_detected: Optional[str]

class ModelAlternative(BaseModel):
    model: str
    estimated_cost: float
    estimated_quality: float
    savings_percent: float

class AdvancedRouter:
    def __init__(
        self,
        registry: ModelRegistry,
        base_router: Router,
        task_detector: TaskTypeDetector,
        constraint_interpreter: ConstraintInterpreter
    ) -> None: ...
    
    def route(
        self,
        prompt: str,
        mode: Literal["autopilot", "guided", "explicit"] = "autopilot",
        quality_preference: Optional[str] = None,
        latency_preference: Optional[str] = None,
        model_override: Optional[str] = None
    ) -> AdvancedRoutingDecision: ...
```

### 12.4 Mode Algorithms

**AUTOPILOT**:
```
1. Detect task type from prompt
2. Look up default constraints for that task type
3. Route using base router with those constraints
4. Return decision with reason "Auto-detected {task_type}"
```

**GUIDED**:
```
1. Detect task type from prompt
2. Interpret user preferences via ConstraintInterpreter
3. Merge: task-type constraints as floor, user preferences as override
4. Route using merged constraints
5. Return decision with reason "User preference + optimization"
```

**EXPLICIT**:
```
1. Validate that model_override exists in registry
2. Execute inference with that specific model
3. Calculate costs for all alternative models
4. Return decision with alternatives list showing potential savings
5. Reason: "User selected {model}; alternatives available"
```

### 12.5 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| EXPLICIT mode with unknown model | Raise `ModelNotFoundError` |
| GUIDED mode with invalid preference value | Raise `ValueError` with allowed values |
| Task detection confidence < 0.3 | Fall back to `general` task type; log warning |

### 12.6 Testing Requirements

- 12+ tests: each mode happy path, mode-specific edge cases, alternative calculation accuracy, unknown model handling.

---

## 13. Component 12: ContextualEmbeddingEngine (Phase 2+)

### 13.1 Purpose

Enhance embeddings by prepending an intelligent context summary (generated by Claude Haiku) before embedding.  This differentiates semantically similar but contextually different queries and improves cache hit accuracy from 89% to 96%.

### 13.2 File

`src/phase2/contextual_embedding.py`

### 13.3 Public Interface

```python
class ContextualEmbeddingEngine:
    def __init__(
        self,
        embedding_engine: EmbeddingEngine,
        context_llm_model: str = "claude-3-5-haiku"
    ) -> None: ...
    
    def generate_context(
        self,
        text: str,
        agent_id: Optional[str] = None,
        task_type: str = "general",
        quality_req: float = 3.5
    ) -> str: ...
    
    def embed_with_context(
        self,
        text: str,
        agent_id: Optional[str] = None,
        task_type: str = "general",
        quality_req: float = 3.5
    ) -> Tuple[np.ndarray, str, str]: ...
    # Returns: (embedding, context_summary, contextual_text)
    
    def retrieve_with_context(
        self,
        query: str,
        agent_id: Optional[str] = None,
        task_type: str = "general",
        top_k: int = 5,
        threshold: float = 0.92
    ) -> Optional[Dict[str, Any]]: ...
```

### 13.4 Context Generation Prompt

```
Text to contextualize: {text[:500]}
Metadata: Agent: {agent_id}, Task: {task_type}, Quality: {quality_req}
Provide 1-2 sentence summary explaining what this is about, 
including the domain, intent, and any critical constraints.
```

Output: 20-50 tokens.  Cost: ~$0.00005 per item.

### 13.5 Cost Impact

| Metric | Value |
|--------|-------|
| Cost per cached item (one-time) | $0.00006 |
| Cost for 1M items | $60 |
| Accuracy improvement | 89% -> 96% |
| Mismatch reduction | 67% |
| ROI | ~1000x |

### 13.6 Testing Requirements

- 8+ tests: context generation, contextual embedding vs plain embedding produces different vectors, retrieval with context matching, threshold enforcement.

---

## 14. Three-Tier Caching Integration Flow

The full cache check order in the updated `InferenceOptimizer`:

```
1. TIER 1: Exact Match
   key = md5(query)
   if key in exact_cache:
       return cached (cost $0, latency <1ms)

2. TIER 2: Semantic Similarity
   result = semantic_cache.get(query, task_type, cost_sensitivity, recompute_cost)
   if result.hit:
       return cached (cost ~$0.0001, latency 10-50ms)

3. TIER 3: Intermediate Reuse
   steps = workflow_decomposer.decompose(prompt, document_id)
   executed_steps = intermediate_cache.execute_workflow(steps, executor)
   if all steps hit cache:
       combine results (cost ~$0, latency 5-20ms)
   elif some steps hit:
       execute remaining; combine all (partial savings)

4. FULL INFERENCE
   Route via AdvancedRouter
   Execute via provider
   Cache result in all applicable tiers
```

---

## 15. Performance Targets (Phase 2)

| Metric | Target |
|--------|--------|
| Tier 1 lookup | < 1 ms |
| Tier 2 embed + search | 10-50 ms |
| Tier 3 lookup + combine | 5-20 ms |
| Total cache overhead (all 3 tiers miss) | < 60 ms |
| Full inference (cache miss) | 200-500 ms (provider-dependent) |
| Cost savings | 85-92% |
| Cache hit rate | 75-90% |
| API call reduction | 85-90% |

### Cost Example (1000 requests/day)

```
Baseline: All GPT-4 = $50/day = $1,500/month

With Phase 2:
  Tier 1 hits: 30% (300 req) = $0
  Tier 2 hits: 35% (350 req) = 350 x $0.001 = $0.35
  Tier 3 hits: 15% (150 req) = 150 x $0.0005 = $0.075
  Misses:      20% (200 req) = 200 x $0.015 = $3.00
  Total: $3.425/day = $103/month (93% savings)
```

---

## 16. Phase 2 Acceptance Criteria

- [ ] All 12 components implemented with full type hints and docstrings
- [ ] 100+ unit tests across all components
- [ ] `pytest --cov --cov-fail-under=90` passes
- [ ] `mypy --strict src/phase2/` reports zero errors
- [ ] Tier 2 cache achieves > 40% additional hit rate on benchmark dataset
- [ ] Tier 3 cache achieves > 15% additional hit rate on multi-step queries
- [ ] All three routing modes produce correct decisions on test scenarios
- [ ] Contextual embedding improves hit accuracy by > 50% on ambiguous query set
- [ ] End-to-end latency overhead < 60 ms for 3-tier cache miss
- [ ] No hardcoded thresholds, model names, or API keys
- [ ] Every component injectable via constructor (no global state)
- [ ] Integration test: 100 queries through full pipeline with mocked providers
