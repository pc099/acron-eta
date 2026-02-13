# Local Testing Guide for Asahi

This guide covers how to test Asahi locally, including all Phase 2 features (Tier 2 semantic caching, AdvancedRouter, etc.).

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Start](#2-quick-start)
3. [Testing Methods](#3-testing-methods)
4. [Testing Phase 2 Features](#4-testing-phase-2-features)
5. [API Endpoints](#5-api-endpoints)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Prerequisites

### Required
- Python 3.10+ installed
- API keys (at least one):
  - `OPENAI_API_KEY` - For LLM inference
  - `COHERE_API_KEY` - For Tier 2 semantic caching (embeddings)
  - `ANTHROPIC_API_KEY` - For Anthropic models (optional)

### Installation

```bash
# Clone/navigate to project
cd d:\claude\asahi

# Install dependencies
pip install -r requirements.txt

# Install Cohere (for Tier 2 caching)
pip install cohere
```

### Environment Setup

Create a `.env` file in the project root:

```bash
# Copy example
cp .env.example .env

# Edit .env and add your keys:
OPENAI_API_KEY=sk-your-key-here
COHERE_API_KEY=your-cohere-key-here
ANTHROPIC_API_KEY=sk-ant-your-key-here  # Optional
```

---

## 2. Quick Start

### Option 1: Run the Test Script (Recommended)

```bash
# Run comprehensive Phase 2 test suite
python test_phase2.py
```

This will test:
- Tier 1 (exact match) caching
- Tier 2 (semantic similarity) caching
- AdvancedRouter modes (AUTOPILOT, GUIDED, EXPLICIT)
- Cache statistics

### Option 2: Start the API Server

```bash
# Start the FastAPI server
python main.py api

# Or use uvicorn directly
uvicorn src.api.app:create_app --factory --reload --port 8000
```

The server will start at `http://localhost:8000`

---

## 3. Testing Methods

### Method 1: Using the Test Script

```bash
# Full Phase 2 test suite
python test_phase2.py

# Test similarity between queries
python test_similarity_detailed.py
```

### Method 2: Using curl

```bash
# Basic inference request
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is Python?",
    "quality_threshold": 3.5
  }'

# With routing mode (AUTOPILOT)
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing",
    "routing_mode": "autopilot"
  }'

# GUIDED mode with preferences
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Summarize this document",
    "routing_mode": "guided",
    "quality_preference": "high",
    "latency_preference": "medium"
  }'

# EXPLICIT mode (select specific model)
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write Python code",
    "routing_mode": "explicit",
    "model_override": "gpt-4o"
  }'
```

### Method 3: Using Python Requests

```python
import requests

# Basic request
response = requests.post(
    "http://localhost:8000/infer",
    json={
        "prompt": "What is machine learning?",
        "routing_mode": "autopilot"
    }
)
print(response.json())

# Check cache hit
result = response.json()
if result["cache_hit"]:
    print(f"Cache hit! Cost saved: ${result['cost']}")
else:
    print(f"Cache miss. Cost: ${result['cost']}")
```

### Method 4: Using the CLI

```bash
# Single inference
python main.py infer --prompt "What is Python?" --quality 3.5

# View metrics
python main.py metrics

# Run tests
python main.py test --num_queries 10
```

---

## 4. Testing Phase 2 Features

### Test Tier 1 (Exact Match) Cache

```bash
# First request (cache miss)
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?"}'

# Second request - exact same prompt (cache hit expected)
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?"}'

# Expected: Second request should show:
# - cache_hit: true
# - cost: 0.0
# - latency_ms: 0.0
# - routing_reason: "Cache hit (exact match)"
```

### Test Tier 2 (Semantic Similarity) Cache

**Prerequisites:** `COHERE_API_KEY` must be set

```bash
# First request - store in Tier 2 cache
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?"}'

# Second request - semantically similar but not exact
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Can you explain what Python is?"}'

# Expected: Second request should show:
# - cache_hit: true
# - cost: 0.0
# - routing_reason: "Cache hit (semantic similarity: 0.81)"
```

**Test Script:**
```bash
python test_phase2.py
# Look for "TEST 2: Tier 2 Semantic Similarity Cache" section
```

### Test AdvancedRouter Modes

#### AUTOPILOT Mode (Auto-detect task type)

```bash
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain quantum computing",
    "routing_mode": "autopilot"
  }'
```

#### GUIDED Mode (User preferences)

```bash
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Summarize this document",
    "routing_mode": "guided",
    "quality_preference": "high",
    "latency_preference": "medium"
  }'
```

#### EXPLICIT Mode (User selects model)

```bash
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write Python code",
    "routing_mode": "explicit",
    "model_override": "gpt-4o"
  }'
```

---

## 5. API Endpoints

### Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 123.4,
  "components": {
    "cache": "healthy",
    "router": "healthy",
    "tracker": "healthy",
    "registry": "healthy",
    "observability": "healthy",
    "governance": "healthy"
  }
}
```

### List Available Models

```bash
curl http://localhost:8000/models
```

### Get Metrics

```bash
curl http://localhost:8000/metrics
```

Response includes:
- Total requests
- Cache hit rate
- Total cost saved
- Cache size

### Analytics Endpoints (Phase 6)

```bash
# Cost breakdown
curl "http://localhost:8000/analytics/cost-breakdown?period=day&group_by=model"

# Trends
curl "http://localhost:8000/analytics/trends?metric=cost&period=day&intervals=30"

# Forecast
curl "http://localhost:8000/analytics/forecast?horizon_days=30&monthly_budget=100"

# Anomalies
curl http://localhost:8000/analytics/anomalies

# Recommendations
curl http://localhost:8000/analytics/recommendations

# Cache performance
curl http://localhost:8000/analytics/cache-performance

# Prometheus metrics
curl http://localhost:8000/analytics/prometheus
```

---

## 6. Testing Scenarios

### Scenario 1: Test Cache Hit Rate

```bash
# Run multiple similar queries
for i in {1..10}; do
  curl -X POST http://localhost:8000/infer \
    -H "Content-Type: application/json" \
    -d "{\"prompt\": \"What is Python?\"}"
done

# Check metrics
curl http://localhost:8000/metrics
# Look for cache_hit_rate (should be high after first request)
```

### Scenario 2: Test Semantic Similarity

```bash
# Store original query
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is machine learning?"}'

# Test semantically similar queries
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Can you explain machine learning?"}'

curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Tell me about ML"}'

curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "How does machine learning work?"}'
```

### Scenario 3: Test Routing Modes

```bash
# Test AUTOPILOT (should auto-detect task type)
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "What is the capital of France?",
    "routing_mode": "autopilot"
  }'
# Check routing_reason - should mention auto-detected task type

# Test GUIDED (should respect preferences)
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Write a poem",
    "routing_mode": "guided",
    "quality_preference": "max",
    "latency_preference": "high"
  }'
# Should select high-quality model

# Test EXPLICIT (should use specified model)
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Hello",
    "routing_mode": "explicit",
    "model_override": "gpt-4o"
  }'
# Should use gpt-4o regardless of other factors
```

---

## 7. Monitoring and Debugging

### Check Logs

The server logs include:
- Cache hits/misses
- Task type detection
- Similarity scores
- Routing decisions

Look for log messages like:
```
INFO: Tier 2 cache hit (similarity: 0.82, task_type: faq)
INFO: Auto-detected 'faq' (confidence=85%)
```

### Enable Debug Logging

```bash
# Set log level to DEBUG
export ASAHI_LOGGING_LEVEL=DEBUG

# Or in .env file
echo "ASAHI_LOGGING_LEVEL=DEBUG" >> .env
```

### Check Cache Statistics

```bash
# Get detailed cache stats
curl http://localhost:8000/metrics | jq '.cache_hit_rate'
curl http://localhost:8000/metrics | jq '.cache_size'
curl http://localhost:8000/metrics | jq '.cache_cost_saved'
```

### Verify Phase 2 Components

```python
# Check if Phase 2 components are initialized
python -c "
from src.api.app import create_app
app = create_app(use_mock=False)
optimizer = app.state.optimizer
print('Tier 2 enabled:', optimizer._enable_tier2)
print('Semantic cache:', 'Yes' if optimizer._semantic_cache else 'No')
print('Advanced router:', 'Yes' if optimizer._advanced_router else 'No')
"
```

---

## 8. Troubleshooting

### Issue: Tier 2 cache not working

**Symptoms:**
- Semantically similar queries don't match
- No "semantic similarity" in routing_reason

**Solutions:**
1. Check `COHERE_API_KEY` is set:
   ```bash
   echo $COHERE_API_KEY  # Linux/Mac
   echo %COHERE_API_KEY%  # Windows
   ```

2. Verify Cohere package installed:
   ```bash
   pip list | grep cohere
   ```

3. Check logs for initialization errors:
   ```bash
   # Look for "Phase 2 components initialization failed"
   ```

4. Verify Phase 2 components initialized:
   ```python
   from src.api.app import create_app
   app = create_app()
   print(app.state.optimizer._semantic_cache is not None)
   ```

### Issue: API key not found

**Error:** `API key not found in environment variable`

**Solutions:**
1. Ensure `.env` file exists in project root
2. Check variable names match exactly (case-sensitive)
3. Restart the server after adding keys
4. Verify keys are loaded:
   ```python
   from dotenv import load_dotenv
   import os
   load_dotenv()
   print(os.getenv("COHERE_API_KEY"))
   ```

### Issue: Low cache hit rate

**Possible causes:**
1. Threshold too high - queries not matching
2. Task type detection incorrect
3. Embeddings not capturing similarity

**Solutions:**
1. Check similarity scores in logs
2. Lower thresholds in `src/embeddings/threshold.py`
3. Use "high" cost_sensitivity for more aggressive caching
4. Verify embeddings are working:
   ```bash
   python test_similarity_detailed.py
   ```

### Issue: Server won't start

**Check:**
1. Port 8000 not in use:
   ```bash
   # Linux/Mac
   lsof -i :8000
   
   # Windows
   netstat -ano | findstr :8000
   ```

2. Dependencies installed:
   ```bash
   pip install -r requirements.txt
   ```

3. Python version:
   ```bash
   python --version  # Should be 3.10+
   ```

---

## 9. Quick Reference

### Common curl Commands

```bash
# Basic inference
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Your question here"}'

# With routing mode
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Question", "routing_mode": "autopilot"}'

# Health check
curl http://localhost:8000/health

# Metrics
curl http://localhost:8000/metrics
```

### Environment Variables

```bash
# Required for LLM inference
OPENAI_API_KEY=sk-...

# Required for Tier 2 semantic caching
COHERE_API_KEY=...

# Optional
ANTHROPIC_API_KEY=sk-ant-...
ASAHI_ENCRYPTION_KEY=...  # For Phase 7 encryption
```

### Test Files

- `test_phase2.py` - Comprehensive Phase 2 test suite
- `test_similarity_detailed.py` - Detailed similarity analysis
- `tests/api/test_app.py` - Unit tests

---

## 10. Next Steps

After local testing:

1. **Verify all features work:**
   - Tier 1 cache hits
   - Tier 2 semantic cache hits
   - AdvancedRouter modes
   - Analytics endpoints

2. **Check performance:**
   - Cache hit rates
   - Cost savings
   - Latency

3. **Review logs:**
   - Task type detection accuracy
   - Similarity scores
   - Routing decisions

4. **Test edge cases:**
   - Very similar queries
   - Different task types
   - Long prompts
   - Special characters

---

## Support

For issues or questions:
1. Check logs for error messages
2. Verify environment variables
3. Run test scripts to isolate issues
4. Check `docs/INTEGRATION_ROADMAP.md` for architecture details
