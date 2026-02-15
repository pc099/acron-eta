# Asahi - Inference Cost Optimizer

Asahi automatically routes LLM requests to the most cost-efficient model while maintaining quality and latency requirements. It provides multi-tier caching, observability, governance, and multi-tenancy for production SaaS use.

## How It Works

```
User Request → Auth → Cache Check (T1/T2/T3) → Route to Optimal Model → Execute → Track & Return
```

1. **Authentication** - API key validation, rate limiting, per-org governance
2. **Cache Check** - Three-tier cache: exact match, semantic similarity, intermediate results
3. **Model Selection** - Routes to cheapest model meeting quality/latency/cost constraints
4. **Inference Execution** - Calls OpenAI or Anthropic API (or mock)
5. **Cost Tracking** - Logs tokens, cost, latency per request
6. **Analytics** - Cost breakdown, trends, forecasting, anomaly detection

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy env file and add your API keys
cp .env.example .env

# Run benchmark (mock mode, no API keys needed)
python main.py benchmark --mock --num_queries 50

# Run a single inference
python main.py infer --prompt "What is Python?" --mock

# Start REST API
python main.py api --mock
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `python main.py infer --prompt "..."` | Single inference request |
| `python main.py test --num_queries 50` | Run test queries |
| `python main.py benchmark` | Baseline vs optimized comparison |
| `python main.py metrics` | View saved metrics |
| `python main.py api` | Start FastAPI REST API |

Add `--mock` to any command to use simulated responses (no API keys required).

## REST API

```bash
# Health check
curl http://localhost:8000/health

# Run inference
curl -X POST http://localhost:8000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?", "quality_threshold": 3.5}'

# View metrics
curl http://localhost:8000/metrics

# Cost breakdown
curl http://localhost:8000/analytics/cost-breakdown?period=day&group_by=model

# Interactive API docs
open http://localhost:8000/docs

# Full API contract and OpenAPI: docs/API_CONTRACT.md
# OpenAPI schema: GET http://localhost:8000/openapi.json
# Quick start: docs/QUICK_START.md | Integration: docs/INTEGRATION_GUIDE.md | ROI/pricing: docs/ROI_PRICING.md
# Observability: docs/PROMETHEUS_SCRAPE.md | Load test: docs/LOAD_TEST.md
```

## Models

| Model | Quality | Input $/1K | Output $/1K | Latency |
|-------|---------|------------|-------------|---------|
| gpt-4-turbo | 4.6/5 | $0.010 | $0.030 | ~200ms |
| claude-opus-4 | 4.5/5 | $0.015 | $0.075 | ~180ms |
| claude-3-5-sonnet | 4.1/5 | $0.003 | $0.015 | ~150ms |

## Configuration

All settings are in `config/config.yaml`. Override any value with environment variables using the `ASAHI_` prefix:

```bash
ASAHI_API_PORT=9000          # overrides api.port
ASAHI_CACHE_TTL_SECONDS=3600 # overrides cache.ttl_seconds
```

Model profiles are in `config/models.yaml`.

## Running Tests

```bash
# All tests (700+)
pytest tests/ -v

# Single module
pytest tests/cache/test_exact.py -v

# With coverage
pytest tests/ --cov=src --cov-fail-under=90
```

## Project Structure

```
asahi/
├── src/
│   ├── config.py              # Central settings (YAML + env overrides)
│   ├── core/optimizer.py      # Orchestrator: cache → route → infer → track
│   ├── models/registry.py     # Model profiles and pricing
│   ├── routing/               # Router, task detector, constraints
│   ├── cache/                 # Exact, semantic, intermediate caching
│   ├── embeddings/            # Embedding engine, similarity, vector store
│   ├── batching/              # Request batching engine
│   ├── optimization/          # Prompt compression, few-shot selection
│   ├── features/              # Feature store integration
│   ├── tracking/tracker.py    # Event logging (JSONL + optional Kafka)
│   ├── observability/         # Metrics, analytics, anomaly detection, forecasting
│   ├── governance/            # Auth, RBAC, audit, compliance, encryption, tenancy
│   └── api/app.py             # FastAPI application factory
├── config/
│   ├── config.yaml            # Application settings
│   └── models.yaml            # LLM model profiles
├── tests/                     # 700+ pytest tests (mirrors src/ structure)
├── docs/                      # Phase specs, wireframes, roadmap
├── main.py                    # CLI entry point
└── requirements.txt
```

## License

MIT
