# Data Models and Schemas

> Canonical data models used across all Asahi components.  
> Every model is defined as a Pydantic BaseModel with strict validation.  
> All timestamps are UTC ISO 8601.  All monetary values are USD.

---

## 1. Core Request/Response Models

### 1.1 InferenceRequest

```python
class InferenceRequest(BaseModel):
    """Incoming inference request from API or SDK."""
    
    # Identity
    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:12]}")
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Prompt
    prompt: str = Field(..., min_length=1, max_length=100000)
    system_prompt: Optional[str] = Field(None, max_length=50000)
    
    # Routing
    routing_mode: Literal["autopilot", "guided", "explicit"] = "autopilot"
    model_override: Optional[str] = None  # EXPLICIT mode only
    quality_preference: Optional[Literal["low", "medium", "high", "max"]] = None
    latency_preference: Optional[Literal["slow", "normal", "fast", "instant"]] = None
    
    # Constraints
    quality_threshold: float = Field(3.5, ge=0.0, le=5.0)
    latency_budget_ms: int = Field(300, ge=50, le=30000)
    cost_budget: Optional[float] = Field(None, ge=0.0)
    
    # Context
    task_id: Optional[str] = None
    task_type: Optional[str] = None  # auto-detected if null
    document_id: Optional[str] = None
    
    # Feature enrichment (Phase 5)
    enrich_with_features: bool = False
    
    # Batching (Phase 3)
    allow_batching: bool = True
    
    # Token optimization (Phase 4)
    optimize_tokens: bool = True
```

### 1.2 InferenceResponse

```python
class InferenceResponse(BaseModel):
    """Response returned to the caller."""
    
    # Identity
    request_id: str
    response_id: str = Field(default_factory=lambda: f"resp_{uuid4().hex[:12]}")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Content
    response: str
    finish_reason: Literal["stop", "length", "error"] = "stop"
    
    # Routing info
    model_used: str
    routing_mode: Literal["autopilot", "guided", "explicit"]
    routing_reason: str
    
    # Cache info
    cache_hit: bool
    cache_tier: Optional[Literal[1, 2, 3]] = None
    cache_similarity: Optional[float] = None  # Tier 2 only
    cache_cached_query: Optional[str] = None  # Tier 2 only
    
    # Cost info
    tokens_input: int
    tokens_output: int
    tokens_total: int
    cost: float
    cost_savings_vs_baseline: float  # vs all-GPT-4
    
    # Latency info
    latency_ms: int
    latency_breakdown: Optional[LatencyBreakdown] = None
    
    # Quality
    predicted_quality: Optional[float] = None
    
    # Alternatives (EXPLICIT mode)
    alternatives: List[ModelAlternative] = []
    
class LatencyBreakdown(BaseModel):
    cache_lookup_ms: int
    routing_ms: int
    inference_ms: int
    post_processing_ms: int
    total_ms: int

class ModelAlternative(BaseModel):
    model: str
    estimated_cost: float
    estimated_quality: float
    savings_percent: float
```

---

## 2. Cache Models

### 2.1 Tier 1: Exact Match Cache Entry

```python
class ExactCacheEntry(BaseModel):
    """Tier 1 cache entry keyed by MD5 hash of user query."""
    
    cache_key: str          # md5 hex digest
    query: str              # original query text
    response: str           # cached response
    model: str              # model that generated this
    cost: float             # original inference cost
    quality_score: Optional[float] = None
    created_at: datetime
    expires_at: datetime
    access_count: int = 0
    last_accessed_at: Optional[datetime] = None
```

### 2.2 Tier 2: Semantic Cache Entry

```python
class SemanticCacheEntry(BaseModel):
    """Tier 2 cache entry with embedding vector."""
    
    cache_id: str           # unique ID (uuid)
    query: str              # original query
    embedding: List[float]  # 1024-dimensional vector
    response: str           # cached response
    model: str
    cost: float
    quality_score: Optional[float] = None
    task_type: str
    context_summary: Optional[str] = None  # Phase 2+ contextual retrieval
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0
    avg_similarity_on_hit: float = 0.0
```

### 2.3 Tier 3: Intermediate Cache Entry

```python
class IntermediateCacheEntry(BaseModel):
    """Tier 3 cache entry for intermediate workflow results."""
    
    cache_key: str          # composite: "{doc_id}:{step_type}:{intent}"
    document_id: Optional[str]
    step_type: str          # "summarize", "extract", "classify"
    intent: str             # specific intent
    result: str             # intermediate result text
    cost: float             # cost to produce this result
    created_at: datetime
    expires_at: datetime
    reuse_count: int = 0
    source_request_id: str  # which request originally produced this
```

---

## 3. Model and Routing Models

### 3.1 ModelProfile

```python
class ModelProfile(BaseModel):
    """Complete profile for an LLM model."""
    
    name: str
    provider: Literal["openai", "anthropic", "mistral", "cohere", "local"]
    api_key_env: str
    cost_per_1k_input_tokens: float = Field(ge=0)
    cost_per_1k_output_tokens: float = Field(ge=0)
    avg_latency_ms: int = Field(gt=0)
    quality_score: float = Field(ge=0, le=5.0)
    max_input_tokens: int = Field(gt=0)
    max_output_tokens: int = Field(gt=0)
    description: str = ""
    availability: Literal["available", "degraded", "unavailable"] = "available"
```

### 3.2 RoutingDecision

```python
class RoutingDecision(BaseModel):
    """Output of the routing engine."""
    
    model_name: str
    mode: Literal["autopilot", "guided", "explicit"]
    score: float
    reason: str
    candidates_evaluated: int
    fallback_used: bool = False
    task_type_detected: Optional[str] = None
    alternatives: List[ModelAlternative] = []
```

### 3.3 RoutingConstraints

```python
class RoutingConstraints(BaseModel):
    """Constraints passed to the router."""
    
    quality_threshold: float = Field(3.5, ge=0, le=5.0)
    latency_budget_ms: int = Field(300, ge=50)
    cost_budget: Optional[float] = Field(None, ge=0)
```

---

## 4. Event and Analytics Models

### 4.1 InferenceEvent

```python
class InferenceEvent(BaseModel):
    """Logged for every inference (hit or miss)."""
    
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    event_type: Literal["inference_complete", "inference_error", "cache_hit"] = "inference_complete"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Request context
    request_id: str
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    task_type: Optional[str] = None
    routing_mode: str = "autopilot"
    
    # Inference details
    model_selected: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    
    # Cache
    cache_hit: bool
    cache_tier: Optional[int] = None
    cache_similarity: Optional[float] = None
    
    # Cost
    cost: float
    baseline_cost: float       # what GPT-4 would have cost
    savings: float             # baseline_cost - cost
    
    # Performance
    latency_ms: int
    
    # Quality
    quality_score: Optional[float] = None
    routing_reason: str = ""
```

### 4.2 AnalyticsEvent (Phase 6)

```python
class AnalyticsEvent(BaseModel):
    """Rich analytics event for Phase 6 observability."""
    
    event_type: str
    event_id: str
    timestamp: datetime
    
    request: RequestSummary
    inference: InferenceSummary
    cache: CacheSummary
    cost: CostSummary
    latency: LatencySummary
    quality: QualitySummary

class RequestSummary(BaseModel):
    request_id: str
    user_id: Optional[str]
    organization_id: Optional[str]
    task_type: Optional[str]
    routing_mode: str

class InferenceSummary(BaseModel):
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int

class CacheSummary(BaseModel):
    hit: bool
    tier: Optional[int]
    similarity: Optional[float]

class CostSummary(BaseModel):
    input_cost: float
    output_cost: float
    total_cost: float
    baseline_cost: float
    savings: float

class LatencySummary(BaseModel):
    total_ms: int
    cache_ms: Optional[int]
    routing_ms: Optional[int]
    inference_ms: Optional[int]

class QualitySummary(BaseModel):
    model_quality: float
    predicted_quality: Optional[float]
    user_satisfaction: Optional[float]
```

---

## 5. Governance Models (Phase 7)

### 5.1 Organization

```python
class Organization(BaseModel):
    org_id: str
    name: str
    plan: Literal["starter", "professional", "enterprise"]
    created_at: datetime
    settings: Dict[str, Any] = {}
    compliance_frameworks: List[str] = []  # ["hipaa", "soc2", "gdpr"]
    data_residency: Optional[str] = None

class OrganizationPolicy(BaseModel):
    org_id: str
    allowed_models: List[str] = []     # empty = all allowed
    blocked_models: List[str] = []
    max_cost_per_day: Optional[float] = None
    max_cost_per_request: Optional[float] = None
    max_requests_per_day: Optional[int] = None
    default_quality_threshold: float = 3.5
    default_latency_budget_ms: int = 300
    require_audit_log: bool = False
    data_residency: Optional[str] = None
```

### 5.2 User and Role

```python
class User(BaseModel):
    user_id: str
    email: str
    org_id: str
    role: str            # "admin", "developer", "viewer", "billing"
    created_at: datetime
    last_active: Optional[datetime] = None
    api_key_prefix: Optional[str] = None

class Role(BaseModel):
    name: str
    permissions: List[str]
    description: str
```

### 5.3 AuditEntry

```python
class AuditEntry(BaseModel):
    entry_id: str
    timestamp: datetime
    org_id: str
    user_id: str
    action: str
    resource: str
    details: Dict[str, Any]
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    result: Literal["success", "denied", "error"]
    data_classification: Literal["public", "internal", "confidential", "restricted"]
    prev_hash: Optional[str] = None  # integrity chain
```

---

## 6. Agent Swarm Models (Phase 8)

```python
class AgentDefinition(BaseModel):
    agent_id: str
    agent_type: str
    task: str
    input_query: str

class AgentState(BaseModel):
    agent_id: str
    agent_type: str
    workflow_id: str
    status: Literal["idle", "working", "completed", "failed"]
    outputs_produced: List[str] = []
    inputs_consumed: List[str] = []
    total_tokens_used: int = 0
    total_cost: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class WorkflowDefinition(BaseModel):
    workflow_id: str
    agents: List[AgentDefinition]
    dependencies: Dict[str, List[str]]  # agent_id -> [depends_on]
    max_parallel: int = 3

class WorkflowResult(BaseModel):
    workflow_id: str
    agent_results: Dict[str, str]
    total_cost: float
    total_tokens: int
    cache_hits: int
    cache_misses: int
    elapsed_ms: int

class AgentCostReport(BaseModel):
    agent_id: str
    agent_type: str
    workflow_id: str
    total_tokens: int
    total_cost: float
    cache_savings: float
    compression_savings: float
    model_used: str
```

---

## 7. Error Models

```python
class AsahiError(BaseModel):
    """Standard error response body."""
    
    error: str              # machine-readable code: "validation_error", "rate_limited", etc.
    message: str            # human-readable description
    details: Dict[str, Any] = {}
    request_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Exception hierarchy
class AsahiException(Exception): ...
class ModelNotFoundError(AsahiException): ...
class NoModelsAvailableError(AsahiException): ...
class ProviderError(AsahiException): ...
class EmbeddingError(AsahiException): ...
class VectorDBError(AsahiException): ...
class ConfigurationError(AsahiException): ...
class FeatureConfigError(AsahiException): ...
class BudgetExceededError(AsahiException): ...
class PermissionDeniedError(AsahiException): ...
class ComplianceViolationError(AsahiException): ...
```

---

## 8. Database Schema (Production)

### 8.1 PostgreSQL Tables

| Table | Purpose | Phase |
|-------|---------|-------|
| `models` | Model profiles | 1 |
| `inference_events` | Event log (append-only) | 1 |
| `cache_entries_tier1` | Exact match cache | 1 |
| `cache_entries_tier2` | Semantic cache metadata | 2 |
| `cache_entries_tier3` | Intermediate cache | 2 |
| `organizations` | Tenant data | 7 |
| `users` | User accounts | 7 |
| `roles` | RBAC roles | 7 |
| `org_policies` | Organization policies | 7 |
| `audit_log` | Immutable audit trail | 7 |
| `api_keys` | Hashed API keys | 7 |
| `agent_states` | Swarm agent states | 8 |
| `workflow_runs` | Workflow execution history | 8 |

### 8.2 Redis Keys

| Key Pattern | TTL | Purpose |
|-------------|-----|---------|
| `cache:t1:{md5_hash}` | 24h | Tier 1 exact match |
| `cache:t3:{composite_key}` | 24h | Tier 3 intermediate |
| `rate:{ip_or_key}` | 60s | Rate limiter counter |
| `budget:{org_id}:daily` | 24h | Daily spend tracker |
| `session:{user_id}` | 1h | User session |

### 8.3 Pinecone Indexes

| Index | Dimension | Metric | Namespace Pattern |
|-------|-----------|--------|-------------------|
| `asahi-cache` | 1024 | cosine | `{org_id}` |
| `asahi-agents` | 1024 | cosine | `{org_id}:{workflow_id}` |
