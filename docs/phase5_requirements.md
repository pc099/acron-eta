# Phase 5: Feature Store Integration -- Component Specification

> **Status**: PLANNED  
> **Timeline**: 8 weeks  
> **Impact**: Quality improvement (enables cheaper models to match expensive ones)  
> **Prerequisite**: Phase 2 complete  

---

## 1. Objective

Integrate with enterprise feature stores (Feast, Tecton, custom) to enrich LLM requests with real-time user and business context.  By providing richer context, cheaper models can produce outputs comparable to expensive models, maintaining savings while improving quality.

### Example

```
Without Feature Store:
  Request: "Recommend a product for this customer"
  Context: just the query
  Model needed: Opus ($0.010/req) -- must reason about customer from scratch
  
With Feature Store:
  Request: "Recommend a product for this customer"
  Enriched context:
    - Last 5 purchases: [shoes, jacket, belt, sneakers, t-shirt]
    - Browsing: currently viewing athletic wear
    - Preference model: casual athletic, budget-conscious
    - Demographics: 25-34, urban
  Model needed: Sonnet ($0.003/req) -- has all the context it needs
  Quality: Same or better (better context = better answer)
```

---

## 2. Component 1: FeatureStoreClient

### 2.1 Purpose

Abstraction layer for connecting to feature stores.  Provides a unified interface regardless of backend (Feast, Tecton, custom HTTP, or local JSON).

### 2.2 File

`src/phase5/feature_store_client.py`

### 2.3 Public Interface

```python
class FeatureVector(BaseModel):
    entity_id: str
    entity_type: str             # "user", "product", "organization"
    features: Dict[str, Any]     # {"purchase_history": [...], "preference_score": 0.8}
    retrieved_at: datetime
    freshness_seconds: float     # age of the data
    source: str                  # "feast", "tecton", "custom", "local"

class FeatureStoreClient(Protocol):
    def get_features(
        self,
        entity_id: str,
        entity_type: str,
        feature_names: List[str]
    ) -> FeatureVector: ...
    
    def get_batch_features(
        self,
        entity_ids: List[str],
        entity_type: str,
        feature_names: List[str]
    ) -> List[FeatureVector]: ...
    
    def health_check(self) -> bool: ...

class FeastClient:
    """Feast online store implementation."""
    def __init__(self, repo_path: str, project: str) -> None: ...

class TectonClient:
    """Tecton feature service implementation."""
    def __init__(self, api_key_env: str, workspace: str) -> None: ...

class LocalFeatureStore:
    """JSON-file backed store for development and testing."""
    def __init__(self, data_path: Path) -> None: ...
```

### 2.4 Configuration

```yaml
feature_store:
  provider: feast          # feast | tecton | custom | local
  feast:
    repo_path: /path/to/feast/repo
    project: asahi
  tecton:
    api_key_env: TECTON_API_KEY
    workspace: production
  local:
    data_path: data/features.json
  
  timeout_ms: 200          # max wait for feature fetch
  fallback_on_timeout: true  # proceed without features if store is slow
```

### 2.5 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Feature store unreachable | If `fallback_on_timeout`, proceed without enrichment; log warning |
| Entity not found | Return empty FeatureVector; log info |
| Stale features (> max freshness) | Return with `freshness_seconds` set; let enricher decide |
| Invalid feature names | Raise `FeatureConfigError` with available feature list |

### 2.6 Testing Requirements

- 10+ tests using `LocalFeatureStore`: get single, get batch, missing entity, stale data, health check.
- Integration test for Feast (gated by `RUN_INTEGRATION_TESTS`).

---

## 3. Component 2: FeatureEnricher

### 3.1 Purpose

Take an incoming request and enrich it with relevant features from the feature store.  Format features into a context block that is prepended to the prompt.

### 3.2 File

`src/phase5/feature_enricher.py`

### 3.3 Public Interface

```python
class EnrichmentResult(BaseModel):
    original_prompt: str
    enriched_prompt: str
    features_used: List[str]
    feature_tokens_added: int
    enrichment_latency_ms: float
    features_available: bool

class FeatureEnricher:
    def __init__(
        self,
        client: FeatureStoreClient,
        config: EnricherConfig
    ) -> None: ...
    
    def enrich(
        self,
        prompt: str,
        user_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        task_type: str = "general",
        context: Optional[Dict[str, Any]] = None
    ) -> EnrichmentResult: ...
    
    def get_relevant_features(
        self,
        task_type: str,
        entity_type: str
    ) -> List[str]: ...
```

#### `EnricherConfig` (Pydantic BaseModel)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `max_feature_tokens` | `int` | `200` | Max tokens to add from features |
| `freshness_threshold_seconds` | `int` | `3600` | Reject features older than this |
| `enabled_task_types` | `List[str]` | `["general","summarization","faq"]` | Tasks that benefit from enrichment |

### 3.4 Enrichment Format

```
[Context from user profile]
- Recent activity: shoes, jacket, belt
- Preference: casual athletic
- Budget: medium
[End context]

{original_prompt}
```

### 3.5 Task-Feature Mapping

| Task Type | Entity | Useful Features |
|-----------|--------|----------------|
| Product recommendation | user | purchase_history, browsing, preferences |
| Customer support | user | tier, recent_tickets, product_owned |
| Content generation | organization | brand_voice, tone, style_guide |
| Code generation | user | language_preferences, framework_history |

### 3.6 Testing Requirements

- 10+ tests: enrichment with available features, missing features, stale features rejection, token limit respect, task-feature mapping, prompt formatting.

---

## 4. Component 3: FeatureMonitor

### 4.1 Purpose

Track feature store health, data freshness, and the impact of enrichment on quality and cost.

### 4.2 File

`src/phase5/feature_monitor.py`

### 4.3 Public Interface

```python
class FeatureMonitor:
    def __init__(self) -> None: ...
    
    def record_enrichment(
        self,
        result: EnrichmentResult,
        inference_quality: Optional[float] = None
    ) -> None: ...
    
    def get_stats(self) -> Dict[str, Any]: ...
    # Returns: {
    #   total_enrichments, successful_enrichments, 
    #   avg_features_used, avg_latency_ms,
    #   quality_with_features, quality_without_features,
    #   feature_store_availability_pct
    # }
    
    def should_enrich(self, task_type: str) -> bool: ...
    # Returns False if feature store has been down or enrichment
    # is not improving quality for this task type.
```

### 4.4 Testing Requirements

- 6+ tests: stat recording, quality comparison, automatic disabling on persistent failure.

---

## 5. Acceptance Criteria

- [ ] FeatureStoreClient supports at least two backends (Feast + Local)
- [ ] FeatureEnricher correctly formats features into prompt context
- [ ] Enrichment adds < 200 tokens by default
- [ ] Feature fetch timeout does not block inference (graceful degradation)
- [ ] FeatureMonitor tracks quality delta with/without enrichment
- [ ] 30+ unit tests with >90% coverage
- [ ] Integration test with Feast on sample data
