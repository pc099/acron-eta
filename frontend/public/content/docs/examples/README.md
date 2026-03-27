# ASAHIO Code Examples

Practical code examples demonstrating common ASAHIO use cases.

---

## Getting Started

All examples require the ASAHIO Python SDK:

```bash
pip install asahio
export ASAHIO_API_KEY="asahio_live_your_key"
```

---

## Examples

### 1. Basic Usage

Demonstrates the fundamentals of using ASAHIO:

```python
# 01_basic_usage.py
from asahio import Asahio

# Initialize client (reads ASAHIO_API_KEY from environment)
client = Asahio()

# Make a simple chat completion request
response = client.chat.completions.create(
    messages=[
        {"role": "user", "content": "What is the capital of France?"}
    ],
    routing_mode="AUTO",  # Let ASAHIO pick the best model
)

# Access the response
print("Response:", response.choices[0].message.content)

# Check ASAHIO metadata
print(f"\nModel used: {response.asahio.model_used}")
print(f"Provider: {response.asahio.provider}")
print(f"Cache hit: {response.asahio.cache_hit}")
print(f"Cost: ${response.asahio.cost_with_asahio:.4f}")
print(f"Saved: ${response.asahio.savings_usd:.4f}")
print(f"Routing mode: {response.asahio.routing_mode}")
```

**Key Concepts:**
- OpenAI-compatible API
- AUTO routing mode
- ASAHIO metadata (cost, savings, model selection)
- Semantic caching

---

### 2. Agent Management

Demonstrates agent lifecycle management:

```python
# 02_agent_management.py
from asahio import Asahio

client = Asahio()

# Create an agent with custom configuration
agent = client.agents.create(
    name="Customer Support Bot",
    description="Handles customer inquiries",
    routing_mode="AUTO",
    intervention_mode="OBSERVE",
    metadata={"team": "support", "version": "1.0"}
)

print(f"Created agent: {agent.name} (ID: {agent.id})")

# Make some tracked calls
for prompt in [
    "How do I reset my password?",
    "What are your business hours?",
    "I need help with my order"
]:
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        agent_id=agent.id,  # Track by agent
    )
    print(f"✓ Processed: {prompt[:30]}...")

# View agent statistics
stats = client.agents.stats(agent.id)
print(f"\nAgent Statistics:")
print(f"  Total calls: {stats.total_calls}")
print(f"  Cache hits: {stats.cache_hits}")
print(f"  Cache hit rate: {stats.cache_hit_rate:.1%}")
print(f"  Avg latency: {stats.avg_latency_ms:.0f}ms")

# Check mode eligibility
eligibility = client.agents.mode_eligibility(agent.id)
print(f"\nMode Eligibility:")
print(f"  Current: {eligibility.current_mode}")
print(f"  Eligible for upgrade: {eligibility.eligible}")
if eligibility.suggested_mode:
    print(f"  Suggested: {eligibility.suggested_mode}")
    print(f"  Reason: {eligibility.reason}")
```

**Key Concepts:**
- Agent creation and configuration
- Mode transitions
- Agent statistics
- Behavioral tracking

---

### 3. Tool Use (Function Calling)

Demonstrates function calling with tools:

```python
# 03_tool_use.py
import json
from asahio import Asahio
from asahio.tools import function_to_tool, extract_tool_calls, format_tool_result

client = Asahio()

# Define a tool function
def get_weather(location: str, units: str = "celsius") -> str:
    """Get the current weather for a location.

    Args:
        location: City name or coordinates
        units: Temperature units (celsius or fahrenheit)
    """
    # In production, call a real weather API
    return f"The weather in {location} is 22°{units[0].upper()} and sunny"

# Convert to OpenAI tool schema
weather_tool = function_to_tool(get_weather)

# Make request with tool
response = client.chat.completions.create(
    messages=[
        {"role": "user", "content": "What's the weather in Paris?"}
    ],
    tools=[weather_tool],
)

# Extract tool calls
tool_calls = extract_tool_calls(response.model_dump())

if tool_calls:
    print(f"Agent wants to call: {tool_calls[0]['name']}")
    print(f"With arguments: {tool_calls[0]['arguments']}")

    # Execute the tool
    args = json.loads(tool_calls[0]['arguments'])
    result = get_weather(**args)

    # Format and submit result
    tool_result = format_tool_result(
        tool_call_id=tool_calls[0]['id'],
        content=result,
        name=tool_calls[0]['name']
    )

    # Continue conversation with tool result
    final_response = client.chat.completions.create(
        messages=[
            {"role": "user", "content": "What's the weather in Paris?"},
            response.choices[0].message.model_dump(),
            tool_result
        ]
    )

    print(f"\nFinal response: {final_response.choices[0].message.content}")
```

**Key Concepts:**
- `function_to_tool()` helper
- Tool execution workflow
- Multi-turn tool conversations
- Tool call extraction

---

### 4. Sessions and Traces

Demonstrates session tracking and observability:

```python
# 04_sessions_and_traces.py
from asahio import Asahio

client = Asahio()

# Create an agent
agent = client.agents.create(
    name="Support Agent",
    routing_mode="AUTO",
    intervention_mode="ASSISTED"
)

# Create a session for tracking multi-turn conversations
session = client.agents.create_session(
    agent_id=agent.id,
    external_session_id="user_123_session_456"
)

print(f"Created session: {session.id}")

# Have a multi-turn conversation
conversation = [
    "I need help with my account",
    "I forgot my password",
    "How long will the reset email take?"
]

for message in conversation:
    response = client.chat.completions.create(
        messages=[{"role": "user", "content": message}],
        agent_id=agent.id,
        session_id=session.external_session_id,
    )
    print(f"\nUser: {message}")
    print(f"Agent: {response.choices[0].message.content[:100]}...")

# View all traces for this agent
traces = client.traces.list_traces(
    agent_id=agent.id,
    limit=10
)

print(f"\n=== Trace History ({len(traces)} traces) ===")
for trace in traces:
    print(f"  {trace.created_at}: {trace.model_used} "
          f"(${trace.cost_with_asahio:.4f}, cache: {trace.cache_hit})")

# Get session graph to see dependencies
graph = client.traces.get_session_graph(session_id=session.id)
print(f"\n=== Session Graph ===")
print(f"Total steps: {graph.step_count}")
for step in graph.steps:
    print(f"  Step {step.step_number}: {step.model_used} "
          f"({step.latency_ms}ms, cache: {step.cache_hit})")
    if step.depends_on:
        print(f"    Depends on steps: {step.depends_on}")
```

**Key Concepts:**
- Session creation
- Conversation history
- Trace querying
- Session graph analysis

---

### 5. Analytics and Cost Monitoring

Demonstrates cost monitoring and analytics:

```python
# 05_analytics_and_cost.py
from datetime import datetime, timedelta
from asahio import Asahio

client = Asahio()

# Get overall analytics for the last 30 days
overview = client.analytics.get_overview(
    period="30d"
)

print("=== Cost Overview (30 days) ===")
print(f"Total cost: ${overview.total_cost:.2f}")
print(f"Total savings: ${overview.total_savings:.2f}")
print(f"Total requests: {overview.total_requests:,}")
print(f"Cache hit rate: {overview.cache_hit_rate:.1%}")
print(f"Avg latency: {overview.avg_latency_ms:.0f}ms")

# Get model breakdown
breakdown = client.analytics.get_model_breakdown(
    start_date=(datetime.now() - timedelta(days=7)).isoformat(),
    end_date=datetime.now().isoformat()
)

print("\n=== Model Usage (7 days) ===")
for model in breakdown.models:
    print(f"{model.model_name}:")
    print(f"  Calls: {model.call_count:,}")
    print(f"  Cost: ${model.total_cost:.2f}")
    print(f"  Tokens: {model.total_tokens:,}")

# Get cache performance
cache_stats = client.analytics.get_cache_performance()

print("\n=== Cache Performance ===")
print(f"Redis hits: {cache_stats.redis_hits:,}")
print(f"Pinecone hits: {cache_stats.pinecone_hits:,}")
print(f"Total hit rate: {cache_stats.total_hit_rate:.1%}")
print(f"Avg lookup time: {cache_stats.avg_lookup_ms:.1f}ms")

# Get intervention stats
intervention_stats = client.interventions.get_stats(days=30)

print("\n=== Intervention Summary ===")
for level_stat in intervention_stats.data:
    print(f"Level {level_stat.level}: {level_stat.count:,} interventions")

# Get fleet overview
fleet = client.interventions.get_fleet_overview()

print("\n=== Fleet Overview ===")
print(f"Agents by mode:")
for mode, count in fleet.mode_distribution.items():
    print(f"  {mode}: {count} agents")

print(f"\nInterventions:")
for action, count in fleet.intervention_summary.items():
    print(f"  {action}: {count}")
```

**Key Concepts:**
- Cost tracking
- Model usage analytics
- Cache performance
- Savings attribution
- Intervention monitoring

---

## Common Patterns

### Pattern 1: Simple Chat with Auto-Routing

```python
from asahio import Asahio

client = Asahio()

response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello"}],
    routing_mode="AUTO",  # Let ASAHIO pick the best model
)

print(response.choices[0].message.content)
print(f"Saved: ${response.asahio.savings_usd:.4f}")
```

### Pattern 2: Agent-Tracked Conversation

```python
# Create agent
agent = client.agents.create(
    name="My Agent",
    routing_mode="AUTO",
    intervention_mode="ASSISTED",
)

# Make tracked calls
response = client.chat.completions.create(
    messages=[...],
    agent_id=agent.id,
)

# View stats
stats = client.agents.stats(agent.id)
print(f"Cache hit rate: {stats.cache_hit_rate:.1%}")
```

### Pattern 3: Tool Use Workflow

```python
from asahio.tools import function_to_tool, extract_tool_calls, format_tool_result

# Define and convert tool
def my_function(param: str) -> str:
    """Function description."""
    return result

tool = function_to_tool(my_function)

# Request with tool
response = client.chat.completions.create(
    messages=[...],
    tools=[tool],
)

# Extract and execute
tool_calls = extract_tool_calls(response.model_dump())
for call in tool_calls:
    result = my_function(**json.loads(call['arguments']))
    tool_result = format_tool_result(
        tool_call_id=call['id'],
        content=result,
        name=call['name']
    )
```

### Pattern 4: Session Management

```python
# Create session
session = client.agents.create_session(
    agent_id="agt_123",
    external_session_id="user_session_xyz"
)

# Use in all related calls
for message in conversation:
    response = client.chat.completions.create(
        messages=[...],
        agent_id="agt_123",
        session_id="user_session_xyz",
    )
```

### Pattern 5: Cost Monitoring

```python
# Get analytics
overview = client.analytics.overview(
    start_date="2026-03-01",
    end_date="2026-03-31"
)

print(f"Total cost: ${overview.total_cost:.2f}")
print(f"Total savings: ${overview.total_savings:.2f}")

# Model breakdown
breakdown = client.analytics.model_breakdown()
for model in breakdown:
    print(f"{model.model_name}: {model.call_count} calls")
```

---

## Advanced Examples

### Streaming Responses

```python
stream = client.chat.completions.create(
    messages=[{"role": "user", "content": "Count to five"}],
    stream=True,
)

for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

### Web Search

```python
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Latest AI news?"}],
    enable_web_search=True,
    web_search_config={
        "max_results": 5,
        "recency_days": 7
    }
)
```

### Fallback Chains

```python
chain = client.chains.create(
    name="Cost-Optimized",
    slots=[
        {"priority": 1, "model": "gpt-4o-mini", "fallback_on_error": True},
        {"priority": 2, "model": "gpt-4o"}
    ]
)

response = client.chat.completions.create(
    messages=[...],
    routing_mode="GUIDED",
    chain_id=chain.id
)
```

### Async Usage

```python
from asahio import AsyncAsahio

async def main():
    async with AsyncAsahio() as client:
        response = await client.chat.completions.create(
            messages=[{"role": "user", "content": "Hello"}]
        )
        print(response.choices[0].message.content)

import asyncio
asyncio.run(main())
```

---

## Error Handling

```python
from asahio import AsahioError

try:
    response = client.chat.completions.create(messages=[...])
except AsahioError as e:
    if "RATE_LIMIT" in str(e):
        print("Rate limit exceeded - waiting before retry")
    elif "BUDGET_EXCEEDED" in str(e):
        print("Monthly budget exceeded")
    else:
        print(f"Error: {e}")
```

---

## Best Practices

1. **Always close clients:**
   ```python
   with Asahio() as client:
       # Use client
       pass
   # Auto-closed
   ```

2. **Use agent IDs for tracking:**
   ```python
   response = client.chat.completions.create(
       messages=[...],
       agent_id="agt_123",  # Track by agent
   )
   ```

3. **Monitor behavioral analytics:**
   ```python
   fingerprint = client.aba.get_fingerprint(agent.id)
   if fingerprint.success_rate < 0.95:
       print("⚠️ Low success rate")
   ```

4. **Set cost constraints:**
   ```python
   client.routing.create_constraint(
       agent_id="agt_123",
       constraint_type="cost_ceiling",
       value=0.01  # Max $0.01 per call
   )
   ```

5. **Use streaming for long responses:**
   ```python
   stream = client.chat.completions.create(
       messages=[...],
       stream=True
   )
   ```

---

## Next Steps

- **[SDK Guide](../sdk/SDK_GUIDE.md)** — Complete SDK documentation
- **[API Reference](../api/API_REFERENCE.md)** — All endpoints
- **[Quickstart](../guides/QUICKSTART.md)** — 5-minute getting started
- **[Best Practices](../guides/BEST_PRACTICES.md)** — Production tips

---

## Support

- **Dashboard:** https://app.asahio.dev
- **Docs:** https://docs.asahio.dev
- **GitHub:** https://github.com/asahio-ai/asahio-python
- **Email:** support@asahio.dev
