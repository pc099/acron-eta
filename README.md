# Asahi - Inference Cost Optimizer

Asahi automatically routes LLM requests to the most cost-efficient model while maintaining quality and latency requirements. It demonstrates **50-70% cost savings** compared to using GPT-4 for all requests.

## How It Works

```
User Request → Cache Check → Route to Optimal Model → Execute → Track & Return
```

1. **Cache Check** - Returns immediately on cache hit
2. **Request Analysis** - Estimates tokens, analyzes constraints
3. **Model Selection** - Routes to cheapest model meeting quality/latency thresholds
4. **Inference Execution** - Calls OpenAI or Anthropic API
5. **Cost Tracking** - Logs tokens, cost, latency per request
6. **Analytics** - Compares against all-GPT-4 baseline

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
| `python main.py api` | Start Flask REST API |

Add `--mock` to any command to use simulated responses (no API keys required).

## REST API

```bash
# Health check
curl http://localhost:5000/health

# Run inference
curl -X POST http://localhost:5000/infer \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is Python?", "quality_threshold": 3.5}'

# View metrics
curl http://localhost:5000/metrics
```

## Models

| Model | Quality | Input $/1K | Output $/1K | Latency |
|-------|---------|------------|-------------|---------|
| gpt-4-turbo | 4.6/5 | $0.010 | $0.030 | ~200ms |
| claude-opus-4 | 4.5/5 | $0.015 | $0.045 | ~180ms |
| claude-3.5-sonnet | 4.1/5 | $0.003 | $0.015 | ~150ms |

## Routing Logic

The router selects the cheapest model that satisfies:
1. Quality threshold (default: 3.5/5)
2. Latency budget (default: 300ms)
3. Optional cost budget

If no model meets all constraints, it falls back to the highest-quality model.

## Running Tests

```bash
pytest tests/ -v
```

## Project Structure

```
asahi/
├── src/
│   ├── optimizer.py   # Core optimizer (cache + route + infer + track)
│   ├── models.py      # Model profiles and pricing
│   ├── routing.py     # Smart routing logic
│   ├── cache.py       # Prompt-based caching
│   ├── tracking.py    # Event logging and analytics
│   └── api.py         # Flask REST API
├── tests/             # Pytest test suite
├── data/              # Test queries and results
├── main.py            # CLI entry point
└── requirements.txt
```

## License

MIT
