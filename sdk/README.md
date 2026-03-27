# ASAHIO Python SDK

[![PyPI version](https://badge.fury.io/py/asahio.svg)](https://badge.fury.io/py/asahio)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

Official Python SDK for the ASAHIO agent control plane — intelligent routing, observability, and reliability for LLM agents.

## What is ASAHIO?

ASAHIO is an LLM observability and routing platform that sits between your agents and LLM providers. It provides:

- **Intelligent Routing** — Auto-select the optimal model based on complexity, cost, latency, and agent behavior
- **Semantic Caching** — Multi-tier cache with Pinecone vector storage for semantic similarity matching
- **Agent Behavioral Analytics (ABA)** — Detect anomalies, track agent fingerprints, and identify hallucinations
- **Intervention Engine** — Augment risky prompts, reroute high-risk calls, or block when authorized
- **Full Observability** — Trace every call, visualize session graphs, track costs and savings

## Installation

```bash
pip install asahio
```

For development:
```bash
cd sdk
pip install -e ".[dev]"
```

## Quick Start

### Gateway (Chat Completions)

```python
from asahio import Asahio

client = Asahio(api_key="asahio_live_your_key")

response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Explain quantum computing"}],
    routing_mode="AUTO",           # Let ASAHIO pick the best model
    intervention_mode="ASSISTED",  # Enable augmentation and rerouting
)

print(response.choices[0].message.content)
print(f"Model used: {response.asahio.model_used}")
print(f"Saved: ${response.asahio.savings_usd}")
```

### Agent Management

```python
# Create an agent
agent = client.agents.create(
    name="Customer Support Agent",
    slug="support-agent",
    routing_mode="AUTO",
    intervention_mode="OBSERVE",
)

# Get agent stats
stats = client.agents.stats(agent.id)
print(f"Total calls: {stats.total_calls}")
print(f"Cache hit rate: {stats.cache_hit_rate:.1%}")

# Check mode eligibility
eligibility = client.agents.mode_eligibility(agent.id)
if eligibility.eligible:
    client.agents.transition_mode(agent.id, target_mode="ASSISTED")

### Tool Use (Function Calling)

```python
from asahio import Asahio
from asahio.tools import function_to_tool, extract_tool_calls, format_tool_result

client = Asahio(api_key="...")

# Define a tool
def get_weather(location: str, unit: str = "celsius") -> str:
    """Get current weather for a location.

    Args:
        location: City name
        unit: Temperature unit (celsius or fahrenheit)
    """
    # Your weather API call here
    return f'{{"temp": 22, "condition": "sunny", "location": "{location}"}}'

# Convert to OpenAI tool schema
tool = function_to_tool(get_weather)

# Call with tool
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "What's the weather in SF?"}],
    tools=[tool],
    tool_choice="auto",  # or "required" or {"type": "function", "function": {"name": "get_weather"}}
)

# Extract tool calls
tool_calls = extract_tool_calls(response.model_dump())

# Execute tool and submit result
if tool_calls:
    for call in tool_calls:
        result = get_weather(location="San Francisco")
        tool_result = format_tool_result(
            tool_call_id=call["id"],
            content=result,
            name=call["name"],
        )
        # Submit tool result in next turn
        response = client.chat.completions.create(
            messages=[
                {"role": "user", "content": "What's the weather in SF?"},
                response.choices[0].message.model_dump(),
                tool_result,
            ],
        )
```

### Web Search

```python
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Latest news on AI regulations?"}],
    enable_web_search=True,
    web_search_config={
        "max_results": 5,
        "recency_days": 7,
    },
)
```

### MCP (Model Context Protocol)

```python
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Analyze this codebase"}],
    mcp_servers=[
        {
            "name": "github",
            "config": {"repo": "asahio-ai/asahio"},
        }
    ],
)
```

### Computer Use (Anthropic)

```python
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Take a screenshot"}],
    enable_computer_use=True,
    computer_use_config={
        "display_width": 1920,
        "display_height": 1080,
    },
)
```

## Observability Examples

### Trace and Session Analytics

```python
# List traces for an agent
traces = client.traces.list(agent_id=agent.id, limit=100)

for trace in traces.data:
    print(f"Call {trace.id}: {trace.model_used} - ${trace.cost:.4f}")

# Get session graph
session = client.traces.get_session(session_id)
graph = client.traces.get_session_graph(session_id)

print(f"Session: {graph.total_steps} steps, {graph.critical_path_steps} critical")
```

### ABA (Agent Behavioral Analytics)

```python
# Get agent fingerprint
fingerprint = client.aba.get_fingerprint(agent.id)
print(f"Observations: {fingerprint.total_observations}")
print(f"Avg complexity: {fingerprint.avg_complexity:.2f}")
print(f"Top tool: {fingerprint.tool_usage_distribution[0] if fingerprint.tool_usage_distribution else 'None'}")

# List anomalies
anomalies = client.aba.list_anomalies(agent_id=agent.id, severity="high")
for anomaly in anomalies:
    print(f"⚠️  {anomaly.anomaly_type}: {anomaly.description}")

# Tag hallucination
client.aba.tag_hallucination(
    call_id="call_123",
    hallucination_detected=True,
    notes="Fabricated citation",
)
```

### Intervention Monitoring

```python
# Get intervention stats
stats = client.interventions.get_stats(agent_id=agent.id)
print(f"Augmented: {stats.augmented_count}")
print(f"Rerouted: {stats.rerouted_count}")
print(f"Blocked: {stats.blocked_count}")

# Fleet-wide intervention overview
overview = client.interventions.fleet_overview()
print(f"Fleet risk score: {overview.avg_risk_score:.2f}")
```

### Cost Analytics

```python
# Get overview
overview = client.analytics.overview(
    start_date="2026-03-01",
    end_date="2026-03-31",
)
print(f"Total cost: ${overview.total_cost:.2f}")
print(f"Total savings: ${overview.total_savings:.2f}")

# Model breakdown
breakdown = client.analytics.model_breakdown()
for model in breakdown:
    print(f"{model.model_name}: {model.call_count} calls, ${model.total_cost:.2f}")

# Cache performance
cache = client.analytics.cache_performance()
print(f"Cache hit rate: {cache.overall_hit_rate:.1%}")
print(f"Tier 1 hits: {cache.tier1_hits}")
print(f"Tier 2 hits: {cache.tier2_hits}")
```

## Routing Modes

ASAHIO supports three routing modes:

### AUTO — Intelligent Six-Factor Routing

```python
response = client.chat.completions.create(
    messages=[...],
    routing_mode="AUTO",  # Let ASAHIO decide
    quality_preference="high",  # or "balanced", "fast"
    latency_preference="normal",  # or "low"
)
```

ASAHIO considers:
1. Prompt complexity
2. Context length
3. Agent behavioral history (ABA)
4. Latency requirements
5. Budget constraints
6. Provider health

### EXPLICIT — Pin to Specific Model

```python
response = client.chat.completions.create(
    messages=[...],
    routing_mode="EXPLICIT",
    model="gpt-4o",  # or custom endpoint
)
```

### GUIDED — Rule-Based Routing

```python
# Create routing constraint
client.routing.create_constraint(
    agent_id=agent.id,
    constraint_type="cost_ceiling",
    value=0.01,  # Max $0.01 per call
    priority=1,
)

response = client.chat.completions.create(
    messages=[...],
    routing_mode="GUIDED",
    agent_id=agent.id,
)
```

## Intervention Modes

### OBSERVE — Watch Only

```python
response = client.chat.completions.create(
    messages=[...],
    intervention_mode="OBSERVE",  # No modifications
)
```

### ASSISTED — Augment + Reroute

```python
response = client.chat.completions.create(
    messages=[...],
    intervention_mode="ASSISTED",
    # ASAHIO may:
    # - Serve from cache
    # - Augment risky prompts
    # - Reroute high-risk calls to stronger models
)
```

### AUTONOMOUS — Full Intervention

```python
# Requires explicit authorization
client.agents.transition_mode(
    agent_id,
    target_mode="AUTONOMOUS",
    operator_authorized=True,
)

response = client.chat.completions.create(
    messages=[...],
    intervention_mode="AUTONOMOUS",
    agent_id=agent.id,
    # ASAHIO may block calls if risk exceeds threshold
)
```

## Async Support

Every resource has an async version:

```python
from asahio import AsyncAsahio

async def main():
    client = AsyncAsahio(api_key="...")

    # All methods are async
    agent = await client.agents.create(name="Async Agent")
    stats = await client.agents.stats(agent.id)

    response = await client.chat.completions.create(
        messages=[{"role": "user", "content": "Hello"}],
    )

    await client.close()

# Context manager
async with AsyncAsahio(api_key="...") as client:
    response = await client.chat.completions.create(...)
```

## Streaming

```python
stream = client.chat.completions.create(
    messages=[{"role": "user", "content": "Count to five"}],
    stream=True,
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

The SDK ignores the gateway's trailing `event: asahio` metadata event to maintain OpenAI compatibility.

## Configuration

### Client Options

```python
client = Asahio(
    api_key="asahio_live_your_key",  # Or set ASAHIO_API_KEY env var
    base_url="https://api.asahio.in",  # Custom gateway URL
    timeout=120.0,  # Request timeout in seconds
    max_retries=2,  # Retry failed requests
    org_slug="your-org",  # Multi-tenant org routing
)
```

### Environment Variables

- `ASAHIO_API_KEY` — API key (preferred)
- `ASAHI_API_KEY` — Backward-compatible alias
- `ACORN_API_KEY` — Legacy alias

## Type Safety

The SDK is fully typed with dataclasses:

```python
from asahio.types import Agent, Fingerprint, Trace, InterventionLog

agent: Agent = client.agents.get("agt_123")
fingerprint: Fingerprint = client.aba.get_fingerprint(agent.id)
trace: Trace = client.traces.get("tr_456")
```

All 40+ types are exported from `asahio.types`.

## Compatibility Aliases

Legacy imports still work:


Response metadata is accessible at both `response.asahio` and `response.asahi`.

## Error Handling

```python
from asahio import Asahio, AsahioError

try:
    response = client.chat.completions.create(...)
except AsahioError as e:
    print(f"ASAHIO error: {e}")
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Type checking
mypy src/

# Linting
ruff check src/
```

## Links

- **Homepage**: https://asahio.in
- **Documentation**: https://www.asahio.in/docs
- **GitHub**: https://github.com/pc099/asahio
- **PyPI**: https://pypi.org/project/asahio/

## License

MIT
