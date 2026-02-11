# Phase 3: Request Batching -- Component Specification

> **Status**: PLANNED  
> **Timeline**: 10 weeks  
> **Additional cost savings**: +10% (total 92-95%)  
> **Prerequisite**: Phase 2 complete  

---

## 1. Objective

Batch compatible inference requests into single API calls to reduce per-request overhead.  Respect individual request latency budgets -- never delay a time-sensitive request for the sake of a batch.

---

## 2. Component 1: BatchEngine

### 2.1 Purpose

Decide whether a request is eligible for batching and determine which batch group it belongs to.

### 2.2 File

`src/phase3/batch_engine.py`

### 2.3 Public Interface

```python
class BatchEligibility(BaseModel):
    eligible: bool
    reason: str
    batch_group: Optional[str]  # e.g. "summarization:sonnet"
    max_wait_ms: int            # how long this request can wait

class BatchEngine:
    def __init__(self, config: BatchConfig) -> None: ...
    
    def evaluate(
        self,
        prompt: str,
        task_type: str,
        model: str,
        latency_budget_ms: int
    ) -> BatchEligibility: ...
```

#### `BatchConfig` (Pydantic BaseModel)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `min_batch_size` | `int` | `2` | Minimum requests to form a batch |
| `max_batch_size` | `int` | `10` | Maximum requests per batch |
| `max_wait_ms` | `int` | `500` | Global max wait before flushing |
| `latency_threshold_ms` | `int` | `200` | Requests with budget below this skip batching |
| `eligible_task_types` | `List[str]` | `["summarization","faq","translation"]` | Only these tasks can be batched |

### 2.4 Eligibility Rules

```
NOT eligible if:
  - latency_budget_ms < config.latency_threshold_ms  (time-critical)
  - task_type not in config.eligible_task_types
  - prompt token count > model's max_input_tokens / max_batch_size

ELIGIBLE otherwise:
  batch_group = "{task_type}:{model}"
  max_wait_ms = min(latency_budget_ms - estimated_inference_ms, config.max_wait_ms)
```

### 2.5 Testing Requirements

- 10+ tests: eligible request, ineligible (tight latency), ineligible (wrong task), batch group assignment, token limit rejection.

---

## 3. Component 2: RequestQueue

### 3.1 Purpose

Thread-safe queue that holds pending requests organized by batch group.  Supports timeout-based flushing.

### 3.2 File

`src/phase3/request_queue.py`

### 3.3 Public Interface

```python
class QueuedRequest(BaseModel):
    request_id: str
    prompt: str
    model: str
    batch_group: str
    enqueued_at: datetime
    deadline: datetime          # enqueued_at + max_wait_ms
    future: asyncio.Future      # resolved when batch completes

class RequestQueue:
    def __init__(self) -> None: ...
    
    def enqueue(self, request: QueuedRequest) -> None: ...
    def get_batch(self, group: str, max_size: int) -> List[QueuedRequest]: ...
    def get_expired_groups(self) -> List[str]: ...
    def size(self, group: Optional[str] = None) -> int: ...
    def remove(self, request_id: str) -> bool: ...
```

### 3.4 Thread Safety

- Use `threading.Lock` for all mutations.
- `get_batch` is atomic: removes requests from queue and returns them.

### 3.5 Testing Requirements

- 8+ tests: enqueue, get_batch respects max_size, expired group detection, thread safety under concurrent access, remove by request_id.

---

## 4. Component 3: BatchScheduler

### 4.1 Purpose

Background process that monitors the queue, forms batches, and triggers execution.  Runs in its own thread/async task.

### 4.2 File

`src/phase3/batch_scheduler.py`

### 4.3 Public Interface

```python
class BatchScheduler:
    def __init__(
        self,
        queue: RequestQueue,
        executor: Callable[[List[QueuedRequest]], List[str]],
        config: BatchConfig
    ) -> None: ...
    
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def flush_group(self, group: str) -> None: ...
    def stats(self) -> Dict[str, Any]: ...
```

### 4.4 Scheduling Algorithm

```
loop every 50ms:
    for group in queue.get_all_groups():
        batch = queue.peek(group)
        
        if len(batch) >= config.max_batch_size:
            execute_batch(group)           # size threshold met
        
        elif any request in batch is past deadline:
            execute_batch(group)           # deadline forcing flush
        
        elif len(batch) >= config.min_batch_size 
             and oldest_request_age > config.max_wait_ms * 0.7:
            execute_batch(group)           # approaching deadline with enough requests
```

### 4.5 Batch Execution

```
1. Pop requests from queue atomically
2. Combine prompts into single API call (provider-specific)
3. Execute batch inference
4. Split response back into per-request results
5. Resolve each request's Future with its result
6. Log batch event with count, total tokens, total cost, per-request savings
```

### 4.6 Performance Targets

| Metric | Target |
|--------|--------|
| Queue enqueue | < 1 ms |
| Scheduler loop | < 5 ms per iteration |
| Batch overhead vs N individual calls | 40-60% cost reduction |

### 4.7 Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Batch API call fails | Fall back to individual calls for each request |
| Single request in batch causes error | Isolate and retry individually; resolve others normally |
| Scheduler thread crashes | Auto-restart; drain queue via individual calls |

### 4.8 Testing Requirements

- 10+ tests: batch formation at size threshold, deadline-based flush, mixed eligibility, error isolation, scheduler start/stop lifecycle.

---

## 5. Acceptance Criteria

- [ ] BatchEngine correctly classifies requests as eligible or not
- [ ] RequestQueue is thread-safe under concurrent load
- [ ] BatchScheduler respects both size and deadline thresholds
- [ ] No request ever exceeds its latency budget due to batching
- [ ] Batch execution achieves measurable cost reduction (>30% per batched request)
- [ ] Error in one batched request does not affect others
- [ ] 30+ unit tests with >90% coverage
- [ ] Integration test: 50 concurrent requests, mixed eligible/ineligible
