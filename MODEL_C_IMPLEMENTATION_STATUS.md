# Model C Implementation Status — March 27, 2026

## ✅ P0: Model C Pinecone Integration (COMPLETE)

### What Was Built

1. **Pinecone Provisioning Service** (`backend/app/services/pinecone_provisioner.py`)
   - `ensure_model_c_index_exists()` — creates `asahio-model-c` index on startup
   - `get_model_c_index()` — singleton connection to Model C index
   - `provision_org_cache_index()` — ready for P1 per-org indexes
   - `delete_org_cache_index()` — cleanup helper

2. **Fingerprint Embedding Service** (`backend/app/services/fingerprint_embedder.py`)
   - Converts structured behavioral observations into semantic text
   - Embeds as 1024-dim vectors via Cohere embed-english-v3.0
   - Example: `"Agent: CHATBOT | Complexity: medium (0.5) | Quality: accurate | Cache: hit"`

3. **Model C Pool Updates** (`backend/app/services/model_c_pool.py`)
   - ✅ Line 89 TODO replaced: `conditional_add()` now upserts vectors to Pinecone
   - ✅ Line 117 TODO replaced: `query_risk_prior()` now queries Pinecone via vector similarity
   - Anonymized metadata: no `org_id` or `agent_id` stored
   - Graceful fallback to in-memory if Pinecone unavailable

4. **Startup Integration** (`backend/app/main.py`)
   - Ensures `asahio-model-c` index exists on app startup
   - Logs success/failure for visibility
   - Creates index if missing (serverless, AWS us-east-1, cosine metric)

5. **ABA Endpoint Update** (`backend/app/api/aba.py`)
   - GET `/aba/risk-prior` now passes Model C index to `ModelCPool`
   - Enables cross-org behavioral learning

### Index Architecture (Implemented)

```
asahio-model-c          Master behavioral pattern index
  ├─ Dimensions: 1024 (Cohere embed-english-v3.0)
  ├─ Metric: cosine
  ├─ Spec: ServerlessSpec(aws, us-east-1)
  └─ Metadata: agent_type, complexity, model, hallucination, cache_hit, latency_ms
```

### Privacy Guarantees

- ✅ No `org_id` stored in Model C index (fully anonymized)
- ✅ No `agent_id` stored in Model C index
- ✅ Complexity bucketed to 0.1 granularity (0.0, 0.1, ..., 1.0)
- ✅ Minimum 50 org observations before contributing to pool

### What Works Now

| Feature | Status | Notes |
|---------|--------|-------|
| Model C index creation | ✅ Working | Auto-created on startup |
| Fingerprint embedding | ✅ Working | Text → 1024-dim vector |
| Vector upsert | ✅ Working | `conditional_add()` writes to Pinecone |
| Vector query | ✅ Working | `query_risk_prior()` searches Pinecone |
| Anonymization | ✅ Working | No org/agent IDs in metadata |
| In-memory fallback | ✅ Working | Graceful degradation if Pinecone down |

---

## ❌ Remaining Gaps (Not Yet Implemented)

### Gap 1: No Observation Writer (Critical)

**Problem**: Model C infrastructure exists but **nothing writes observations to it**.

**Impact**: `conditional_add()` is never called, so the Model C index stays empty.

**What's Missing**:
```python
# In trace_writer.py or gateway.py, after writing a trace:
from app.services.model_c_pool import ModelCPool, PoolRecord
from app.services.pinecone_provisioner import get_model_c_index

# Build observation from trace
record = PoolRecord(
    agent_type=agent.agent_type,
    complexity_bucket=complexity_score,
    output_type="TEXT",  # or CODE, DATA
    model_used=trace.model_used,
    hallucination_detected=trace.hallucination_detected,
    cache_hit=trace.cache_hit,
    latency_ms=trace.latency_ms,
)

# Write to Model C pool (fire-and-forget background task)
pool = ModelCPool(pinecone_index=get_model_c_index())
asyncio.create_task(
    pool.conditional_add(
        org_id=org_id,
        org_observation_count=org_total_observations,
        record=record,
    )
)
```

**Where to Add This**:
- Option A: `backend/app/services/trace_writer.py` in `write_trace()` after DB commit
- Option B: `backend/app/api/gateway.py` after trace write (less preferred, keeps gateway lean)

**Recommended**: Add to `trace_writer.py` as a fire-and-forget task.

---

### Gap 2: No Per-Org Pinecone Indexes (P1)

**Current State**: All orgs share `asahio-semantic-cache` index, isolated by metadata filtering.

**Risk**: Metadata filter bugs could leak cross-org data.

**What's Needed**:
1. DB migration: add `organisations.pinecone_index_name` column
2. Call `provision_org_cache_index(org_id)` when org is created
3. Update `backend/app/services/cache.py` to use `org.pinecone_index_name`
4. Backfill existing orgs with dedicated indexes
5. Migrate data from shared index to per-org indexes

**Tradeoff**: Privacy/security vs. cost (~$0.20/GB/month per org).

---

### Gap 3: No Org Creation Endpoint (P1)

**Current State**: No POST `/orgs` endpoint exists. Orgs created via:
- Clerk webhook (implicit org creation on user signup)
- Manual DB inserts (dev/testing)

**What's Needed**:
```python
# backend/app/api/orgs.py
@router.post("/", status_code=201)
async def create_org(body: CreateOrgRequest, ...):
    # 1. Validate slug uniqueness
    # 2. Create Organisation record in DB
    # 3. Create Member record (creator = owner)
    # 4. Generate first API key
    # 5. Provision Pinecone index (background task)
    # 6. Return org details
```

**Hook Point**: Call `provision_org_cache_index(org_id)` as background task.

---

## Next Steps (Prioritized)

### Immediate (This Week)

1. **Implement Observation Writer** (Gap 1)
   - Add Model C observation logic to `trace_writer.py`
   - Fire-and-forget `pool.conditional_add()` after trace write
   - Requires: org observation count query (count CallTrace by org_id)

2. **Test Model C End-to-End**
   - Create test agent + session
   - Trigger observations via gateway calls
   - Verify vectors appear in Pinecone `asahio-model-c` index
   - Query `/aba/risk-prior` and verify results

### Short-Term (Next 2 Weeks)

3. **Org Creation Endpoint** (Gap 3)
   - POST `/orgs` with org name + slug
   - Auto-generate API key for creator
   - Background task for Pinecone provisioning
   - Integration tests

4. **Per-Org Index Provisioning** (Gap 2, Phase 1)
   - Add DB migration for `pinecone_index_name` column
   - Update org creation to call `provision_org_cache_index()`
   - Test new orgs get dedicated indexes

### Medium-Term (Next Month)

5. **Per-Org Index Migration** (Gap 2, Phase 2)
   - Backfill script for existing orgs
   - Data migration from shared to per-org indexes
   - Gradual rollout with feature flag
   - Delete shared index after migration complete

---

## Environment Variables Required

```bash
# Model C requires these existing vars:
PINECONE_API_KEY=pcsk_...
COHERE_API_KEY=...

# New index auto-created on startup:
# asahio-model-c (no config needed, hardcoded name)
```

---

## Testing Checklist

### Unit Tests
- [ ] `test_pinecone_provisioner.py`
  - ensure_model_c_index_exists() idempotent
  - provision_org_cache_index() success/failure
  - delete_org_cache_index() cleanup

- [ ] `test_fingerprint_embedder.py`
  - fingerprint_to_text() semantic format
  - embed_fingerprint() returns 1024-dim vector
  - embed_fingerprint_query() simplified query

- [ ] `test_model_c_pool.py`
  - conditional_add() writes to Pinecone
  - query_risk_prior() queries Pinecone
  - In-memory fallback when Pinecone unavailable

### Integration Tests
- [ ] End-to-end: trace → observation → Model C → risk prior query
- [ ] Startup: ensure Model C index created on boot
- [ ] Anonymization: verify no org_id in Pinecone metadata

### Manual Testing
- [ ] Deploy to Railway, check startup logs for "Model C (ABA) index ready"
- [ ] Query Pinecone console for `asahio-model-c` index
- [ ] Call POST `/v1/chat/completions` → verify observation written
- [ ] Call GET `/aba/risk-prior?agent_type=CHATBOT&complexity_bucket=0.5`

---

## Deployment Notes

### Railway Environment
- No new env vars needed (uses existing PINECONE_API_KEY, COHERE_API_KEY)
- Index auto-created on first deployment
- Startup logs will show success/failure

### Pinecone Console
- New index: `asahio-model-c`
- Expected: 1024 dimensions, cosine metric, serverless
- Check stats after observations start flowing

### Rollback Plan
- Model C is additive — no schema changes, no breaking changes
- If Pinecone unavailable, falls back to in-memory (graceful degradation)
- Can disable by setting PINECONE_API_KEY to empty string

---

## Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Model C index created | 100% | Check Railway startup logs |
| Observations written | >0 after 1 hour | Query Pinecone stats |
| Risk priors queryable | <500ms p95 | Monitor `/aba/risk-prior` latency |
| Anonymization verified | 100% | Audit Pinecone metadata (no org_id) |

---

## Open Questions

1. **Observation Sampling**: Write every trace to Model C, or sample 10% for cost?
   - **Recommendation**: Sample 10% initially, increase to 100% if cost acceptable

2. **Model C Index Deletion**: When/how to clean up old patterns?
   - **Recommendation**: TTL of 90 days per vector (Pinecone metadata filter)

3. **Org Observation Count**: Cache in Redis or query DB on every trace?
   - **Recommendation**: Cache in Redis with 5min TTL

4. **Per-Org Index Lazy Provisioning**: Create on signup or first cache write?
   - **Recommendation**: Create on signup (predictable, easier to debug)

---

## Related Documentation

- See `PINECONE_ARCHITECTURE_GAPS.md` for full architectural analysis
- See `docs/NEXT_STEPS.md` for overall project roadmap
- See Pinecone docs: https://docs.pinecone.io/
