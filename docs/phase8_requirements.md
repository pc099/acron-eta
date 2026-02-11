# Phase 8: Agent Swarm Optimization -- Component Specification

> **Status**: PLANNED  
> **Timeline**: 14 weeks  
> **Cost savings target**: 92-98% vs naive agent swarms  
> **Additional savings vs Phases 1-4**: 46%  
> **Prerequisite**: Phases 1-2 complete, Phase 2+ contextual retrieval  

---

## 1. Objective

Extend Asahi to understand, optimise, and govern multi-agent architectures.  Agent swarms (CrewAI, LangGraph, AutoGen) create exponential cost through redundant context passing between agents.  Phase 8 caches inter-agent communication, compresses shared context, and routes each agent to its optimal model.

### The Problem

```
Traditional Multi-Agent Flow (no optimization):
  Agent A generates message (2000 tokens)
  Agent B receives full message (2000 tokens) + processes
  Agent C receives full message (2000 tokens) + processes
  Agent D receives full message (2000 tokens) + processes
  Total: 8,000 tokens for one "fact"

With Phase 8:
  Agent A generates message (2000 tokens) -> store in cache
  Agent B requests info -> cache hit -> compressed (200 tokens)
  Agent C requests info -> cache hit -> compressed (200 tokens)
  Agent D requests info -> cache hit -> compressed (200 tokens)
  Total: 2,600 tokens = 67% reduction
```

### Cost Impact

| Scenario | Cost/workflow | Monthly (1000/day) | Annual |
|----------|--------------|-------------------|--------|
| No optimization | $0.104 | $3,120 | $37,440 |
| Phases 1-4 | $0.015 | $450 | $5,400 |
| Phase 8 | $0.008 | $240 | $2,880 |

---

## 2. Component 1: AgentContextualCache

### 2.1 Purpose

Store and retrieve agent outputs with context-aware embeddings.  This is the core innovation -- when Agent A produces output, it is cached with contextual metadata so that Agents B, C, D can retrieve exactly what they need without full re-transmission.

### 2.2 File

`src/phase8/agent_contextual_cache.py`

### 2.3 Public Interface

```python
class AgentOutput(BaseModel):
    agent_id: str
    agent_type: str           # "ProductManager", "Architect", "CodeGenerator", etc.
    task_type: str
    output: str
    input_query: str
    token_count: int
    timestamp: datetime

class CachedAgentOutput(BaseModel):
    cache_id: str
    agent_output: AgentOutput
    context_summary: str
    compressed_output: Optional[str]
    embedding: List[float]
    hit_count: int
    created_at: datetime

class AgentContextualCache:
    def __init__(
        self,
        contextual_embedder: ContextualEmbeddingEngine,
        vector_db: VectorDatabase,
        compressor: InterAgentMessageCompressor
    ) -> None: ...
    
    def cache_agent_output(self, output: AgentOutput) -> CachedAgentOutput: ...
    
    def retrieve_for_agent(
        self,
        requesting_agent_type: str,
        query: str,
        task_type: str,
        source_agent_type: Optional[str] = None,
        top_k: int = 3,
        threshold: float = 0.93
    ) -> Optional[str]: ...
    
    def invalidate_agent(self, agent_id: str) -> int: ...
    def invalidate_workflow(self, workflow_id: str) -> int: ...
    def stats(self) -> Dict[str, Any]: ...
```

### 2.4 Cache Flow

```
cache_agent_output:
  1. Generate context summary via ContextualEmbeddingEngine
     "[Architect:SystemDesign] High-level system architecture for e-commerce"
  2. Embed output with context
  3. If output > 5000 chars: compress via InterAgentMessageCompressor
  4. Store in vector DB with metadata:
     {agent_id, agent_type, task_type, context_summary, 
      original_size, compressed_size, workflow_id, timestamp}

retrieve_for_agent:
  1. Embed query with requesting agent's context
  2. Search vector DB with optional filter on source_agent_type
  3. For each result above threshold:
     - Return compressed version if available (saves tokens for requester)
     - Return full output if compressed version would lose critical detail
  4. Return None if no match found
```

### 2.5 Testing Requirements

- 12+ tests: cache output, retrieve by another agent, threshold filtering, compression trigger, invalidation by agent and workflow, stats tracking.

---

## 3. Component 2: InterAgentMessageCompressor

### 3.1 Purpose

Analyse agent outputs and extract key information tailored for downstream agents.  Reduce token count by 80-90% while preserving actionable content.

### 3.2 File

`src/phase8/message_compressor.py`

### 3.3 Public Interface

```python
class CompressionResult(BaseModel):
    original_text: str
    compressed_text: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    key_facts_preserved: int
    strategy: str

class InterAgentMessageCompressor:
    def __init__(self, config: CompressorConfig) -> None: ...
    
    def compress(
        self,
        text: str,
        source_agent_type: str,
        target_agent_type: str,
        task_type: str
    ) -> CompressionResult: ...
    
    def compress_for_multiple(
        self,
        text: str,
        source_agent_type: str,
        target_agent_types: List[str]
    ) -> Dict[str, CompressionResult]: ...
```

### 3.4 Compression Strategy Per Agent Pair

| Source | Target | Strategy | Ratio |
|--------|--------|----------|-------|
| Architect | CodeGenerator | Extract interfaces, APIs, constraints | 80-90% |
| Architect | QA | Extract requirements, acceptance criteria | 85% |
| ProductManager | Architect | Extract requirements, priorities | 75% |
| CodeGenerator | CodeReviewer | Extract code + critical context only | 60% |
| Any | Any (default) | Extractive summarization | 70% |

### 3.5 Testing Requirements

- 10+ tests: each agent pair compression, token counting accuracy, compression ratio targets met, round-trip information preservation spot check.

---

## 4. Component 3: AgentStateManagement

### 4.1 Purpose

Track what information each agent has computed, which agents have consumed which outputs, and prevent redundant computation across the swarm.

### 4.2 File

`src/phase8/agent_state.py`

### 4.3 Public Interface

```python
class AgentState(BaseModel):
    agent_id: str
    agent_type: str
    workflow_id: str
    status: Literal["idle", "working", "completed", "failed"]
    outputs_produced: List[str]     # cache IDs
    inputs_consumed: List[str]      # cache IDs of outputs this agent used
    total_tokens_used: int
    total_cost: float
    started_at: Optional[datetime]
    completed_at: Optional[datetime]

class AgentStateManager:
    def __init__(self) -> None: ...
    
    def register_agent(self, agent_id: str, agent_type: str, workflow_id: str) -> None: ...
    def update_status(self, agent_id: str, status: str) -> None: ...
    def record_output(self, agent_id: str, cache_id: str, tokens: int, cost: float) -> None: ...
    def record_input(self, agent_id: str, cache_id: str) -> None: ...
    
    def get_state(self, agent_id: str) -> AgentState: ...
    def get_workflow_states(self, workflow_id: str) -> List[AgentState]: ...
    
    def is_redundant(
        self,
        agent_type: str,
        task_type: str,
        workflow_id: str
    ) -> Tuple[bool, Optional[str]]: ...
    # Returns: (is_redundant, existing_cache_id if so)
    
    def get_dependencies(self, agent_id: str) -> List[str]: ...
    # Which agent outputs does this agent need before it can start?
```

### 4.4 Redundancy Detection

```
is_redundant(agent_type, task_type, workflow_id):
  1. Check if any agent of same type in same workflow already completed same task
  2. If yes, return (True, cache_id of that output)
  3. Orchestrator can then skip execution and use cached output
```

### 4.5 Testing Requirements

- 10+ tests: register, status lifecycle, output/input tracking, redundancy detection, workflow-scoped queries.

---

## 5. Component 4: AgentSpecializationRouter

### 5.1 Purpose

Route each agent type to its optimal model based on the agent's role requirements.  A ProductManager does not need GPT-4; a QA agent does not need Opus.

### 5.2 File

`src/phase8/agent_router.py`

### 5.3 Public Interface

```python
class AgentProfile(BaseModel):
    agent_type: str
    quality_req: float
    latency_budget_ms: int
    preferred_models: List[str]
    cost_sensitivity: Literal["high", "medium", "low"]

class AgentSpecializationRouter:
    def __init__(
        self,
        registry: ModelRegistry,
        base_router: Router
    ) -> None: ...
    
    def register_profile(self, profile: AgentProfile) -> None: ...
    def route_agent(self, agent_type: str) -> RoutingDecision: ...
    def get_all_profiles(self) -> Dict[str, AgentProfile]: ...
```

### 5.4 Default Agent Profiles

| Agent Type | Quality Req | Latency Budget | Preferred Models | Cost Sensitivity |
|-----------|------------|----------------|------------------|-----------------|
| ProductManager | 3.5 | 2000 ms | sonnet, opus | high |
| Architect | 4.3 | 1000 ms | opus, gpt-4 | low |
| CodeGenerator | 4.2 | 300 ms | gpt-4-turbo, opus | medium |
| CodeReviewer | 3.9 | 600 ms | sonnet, opus | medium |
| QA | 3.0 | 200 ms | mistral, sonnet | high |
| DatabaseDesigner | 4.0 | 500 ms | opus, sonnet | medium |
| APIDesigner | 4.0 | 500 ms | opus, sonnet | medium |
| FrontendDesigner | 3.8 | 500 ms | sonnet, gpt-4-turbo | medium |

### 5.5 Testing Requirements

- 8+ tests: each default profile routes to expected model, custom profile registration, unknown agent type fallback.

---

## 6. Component 5: AgentCostAttributor

### 6.1 Purpose

Track and attribute costs per agent, per workflow, per organization.  Enable billing, governance, and optimization decisions.

### 6.2 File

`src/phase8/cost_attributor.py`

### 6.3 Public Interface

```python
class AgentCostReport(BaseModel):
    agent_id: str
    agent_type: str
    workflow_id: str
    total_tokens: int
    total_cost: float
    cache_savings: float      # how much was saved by cache hits
    compression_savings: float # how much was saved by compression
    model_used: str

class AgentCostAttributor:
    def __init__(self) -> None: ...
    
    def record_cost(
        self,
        agent_id: str,
        agent_type: str,
        workflow_id: str,
        tokens: int,
        cost: float,
        model: str,
        cache_hit: bool,
        compressed: bool
    ) -> None: ...
    
    def get_agent_report(self, agent_id: str) -> AgentCostReport: ...
    def get_workflow_report(self, workflow_id: str) -> List[AgentCostReport]: ...
    def get_type_summary(self) -> Dict[str, Dict[str, float]]: ...
    # Returns: {"Architect": {"total_cost": 5.0, "avg_cost": 0.05, "cache_rate": 0.8}, ...}
    
    def get_top_spenders(self, limit: int = 10) -> List[AgentCostReport]: ...
```

### 6.4 Testing Requirements

- 8+ tests: cost recording, per-agent report, workflow rollup, type summary aggregation.

---

## 7. Component 6: AgentSwarmOrchestrator

### 7.1 Purpose

Coordinate agent execution within a workflow.  Decide execution order, identify parallelisation opportunities, and ensure maximum cache reuse.

### 7.2 File

`src/phase8/swarm_orchestrator.py`

### 7.3 Public Interface

```python
class WorkflowDefinition(BaseModel):
    workflow_id: str
    agents: List[AgentDefinition]
    dependencies: Dict[str, List[str]]  # agent_id -> [depends_on_agent_ids]
    max_parallel: int

class AgentDefinition(BaseModel):
    agent_id: str
    agent_type: str
    task: str
    input_query: str

class WorkflowResult(BaseModel):
    workflow_id: str
    agent_results: Dict[str, str]   # agent_id -> output
    total_cost: float
    total_tokens: int
    cache_hits: int
    cache_misses: int
    elapsed_ms: int

class AgentSwarmOrchestrator:
    def __init__(
        self,
        cache: AgentContextualCache,
        state_manager: AgentStateManager,
        router: AgentSpecializationRouter,
        cost_attributor: AgentCostAttributor,
        optimizer: InferenceOptimizer
    ) -> None: ...
    
    def execute_workflow(
        self,
        workflow: WorkflowDefinition
    ) -> WorkflowResult: ...
    
    def get_execution_plan(
        self,
        workflow: WorkflowDefinition
    ) -> List[List[str]]: ...
    # Returns: execution tiers -- agents in same tier run in parallel
    # [[a1, a2], [a3], [a4, a5]]  means a1,a2 parallel, then a3, then a4,a5 parallel
```

### 7.4 Execution Algorithm

```
1. Build dependency graph from workflow definition
2. Topological sort into execution tiers
3. For each tier (sequential):
   For each agent in tier (parallel):
     a. Check if agent's task is redundant (state_manager.is_redundant)
        If yes: use cached output, skip execution
     b. Retrieve any required inputs from AgentContextualCache
     c. Route agent to optimal model (AgentSpecializationRouter)
     d. Execute inference via optimizer
     e. Cache output (AgentContextualCache.cache_agent_output)
     f. Update state (AgentStateManager)
     g. Record cost (AgentCostAttributor)
4. Combine all agent outputs into WorkflowResult
```

### 7.5 Testing Requirements

- 12+ tests: simple linear workflow, parallel agents, dependency resolution, cache hit skips execution, full workflow end-to-end with mocked inference.

---

## 8. Component 7: AgentMeshMonitor

### 8.1 Purpose

Observe inter-agent communication patterns, track cache reuse rates, and surface optimisation opportunities.

### 8.2 File

`src/phase8/mesh_monitor.py`

### 8.3 Public Interface

```python
class MeshMetrics(BaseModel):
    total_workflows: int
    total_agent_calls: int
    inter_agent_cache_hit_rate: float
    avg_compression_ratio: float
    redundant_computations_avoided: int
    total_tokens_saved: int
    total_cost_saved: float
    busiest_agent_types: Dict[str, int]
    most_reused_outputs: List[Dict[str, Any]]

class AgentMeshMonitor:
    def __init__(self, state_manager: AgentStateManager, cost_attributor: AgentCostAttributor) -> None: ...
    
    def record_communication(
        self,
        source_agent: str,
        target_agent: str,
        tokens_original: int,
        tokens_compressed: int,
        cache_hit: bool
    ) -> None: ...
    
    def get_metrics(self) -> MeshMetrics: ...
    def get_communication_graph(self) -> Dict[str, List[Dict[str, Any]]]: ...
    # Returns adjacency list: {"Architect": [{"target": "CodeGen", "frequency": 50, "avg_tokens": 200}]}
    
    def get_optimization_suggestions(self) -> List[str]: ...
```

### 8.4 Testing Requirements

- 8+ tests: communication recording, metrics aggregation, graph generation, suggestion logic.

---

## 9. Component 8: AgentFailureRecovery

### 9.1 Purpose

When an agent fails, use cached successful attempts (from same or similar workflows) instead of retrying with full context.

### 9.2 File

`src/phase8/failure_recovery.py`

### 9.3 Public Interface

```python
class RecoveryResult(BaseModel):
    recovered: bool
    source: str            # "cache_exact", "cache_similar", "retry", "failed"
    output: Optional[str]
    confidence: float
    original_error: str

class AgentFailureRecovery:
    def __init__(
        self,
        cache: AgentContextualCache,
        state_manager: AgentStateManager
    ) -> None: ...
    
    def recover(
        self,
        failed_agent: AgentState,
        error: Exception,
        max_retries: int = 2
    ) -> RecoveryResult: ...
```

### 9.4 Recovery Strategy

```
1. Check cache for exact match from previous workflow runs
   If found: return cached output (confidence 0.95)
2. Check cache for similar output from same agent type
   If found with similarity > 0.90: return (confidence 0.80)
3. Retry with exponential backoff (up to max_retries)
   If succeeds: return (confidence 1.0)
4. Return failed with original error
```

### 9.5 Testing Requirements

- 8+ tests: cache exact recovery, similar recovery, retry success, all attempts fail, confidence scoring.

---

## 10. Success Metrics

| Metric | Target |
|--------|--------|
| Inter-agent context reuse rate | > 85% |
| Cache hit accuracy (contextual) | > 94% |
| Cost per agent-to-agent communication | < $0.0001 |
| Overall swarm cost reduction vs Phases 1-4 | 46% improvement |
| Redundant computation elimination | > 80% |
| Agent latency degradation | None (cache is faster than recompute) |
| Message compression ratio | 80-90% |

---

## 11. Acceptance Criteria

- [ ] All 8 components implemented with full type hints and docstrings
- [ ] AgentContextualCache achieves > 85% reuse rate on benchmark swarm
- [ ] InterAgentMessageCompressor achieves 80%+ compression
- [ ] AgentSpecializationRouter routes each agent type to correct model
- [ ] SwarmOrchestrator correctly handles parallel and sequential agents
- [ ] FailureRecovery successfully recovers from cached outputs
- [ ] CostAttributor produces accurate per-agent billing reports
- [ ] MeshMonitor generates actionable optimization suggestions
- [ ] 70+ unit tests with >90% coverage
- [ ] End-to-end swarm test: 5-agent workflow with mocked inference
- [ ] No global state; all components injectable via constructor
