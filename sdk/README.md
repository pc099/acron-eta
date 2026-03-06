# Asahi Python SDK

Python client for the Asahi inference API — drop-in style for OpenAI’s chat completions, with cost optimization, caching, and routing.

## Install

From the repo (editable):

```bash
cd sdk
pip install -e .
```

Or install from PyPI (after publishing):

```bash
pip install asahi-ai
```

## Publishing to PyPI

### 1. Prerequisites

- [PyPI](https://pypi.org) account (and [Test PyPI](https://test.pypi.org) for testing).
- Build tools: `pip install build twine`

### 2. Bump version (optional)

Edit `pyproject.toml` and set a new `version` (e.g. `0.1.1`) before each release.

### 3. Build the package

From the **`sdk`** directory:

```bash
cd sdk
python -m build
```

This creates `dist/asahi_ai-0.1.0-py3-none-any.whl` and `dist/asahi-ai-0.1.0.tar.gz`.

### 4. Upload to Test PyPI (recommended first)

```bash
python -m twine upload --repository testpypi dist/*
```

When prompted, use your Test PyPI username and password (or token). Then try installing:

```bash
pip install --index-url https://test.pypi.org/simple/ asahi-ai
```

### 5. Upload to real PyPI

When ready for production:

```bash
python -m twine upload dist/*
```

Use your PyPI username and password, or an [API token](https://pypi.org/manage/account/token/) (recommended).

### 6. Install from PyPI

Anyone can then install with:

```bash
pip install asahi-ai
```

Then in Python: `from acorn import Acorn`

---

## Quick start

### 1. Get an API key

Create an API key in the Asahi dashboard: **API Keys** → **Create key**. Use the key (e.g. `acron_live_...` or `asahi_live_...`) for all requests.

### 2. Sync usage

```python
from acorn import Acorn

# API key from env ACORN_API_KEY, or pass explicitly
client = Acorn(api_key="acron_live_xxxxxxxx")

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is Python?"}],
)

print(response.choices[0].message.content)
print(f"Model used: {response.asahi.model_used}")
print(f"Savings: ${response.asahi.savings_usd:.4f} ({response.asahi.savings_pct:.0f}%)")
```

### 3. Async usage

```python
from acorn import AsyncAcorn

client = AsyncAcorn(api_key="acron_live_xxxxxxxx")

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What is Python?"}],
)

print(response.choices[0].message.content)
print(f"Cache hit: {response.asahi.cache_hit}")
```

### 4. Use your own backend URL

Point the client at your Asahi API (e.g. self-hosted or staging):

```python
client = Acorn(
    api_key="acron_live_xxxxxxxx",
    base_url="https://your-asahi-api.example.com",
)
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
)
```

### 5. Optional parameters

- **`routing_mode`** — `"AUTOPILOT"` (default), `"GUIDED"`, or `"EXPLICIT"`.
- **`quality_preference`** — `"high"` (default), `"balanced"`, `"low"`.
- **`latency_preference`** — `"normal"` (default), `"low"`, `"high"`.
- **`stream`** — `True` for streaming; returns a stream of chunks.
- **`org_slug`** — Organisation slug sent as `X-Org-Slug` when using multi-tenant dashboard.

Example:

```python
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Explain async in Python"}],
    routing_mode="AUTOPILOT",
    quality_preference="high",
    latency_preference="low",
)
```

### 6. Streaming

```python
stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Count to 5"}],
    stream=True,
)
for chunk in stream:
    if chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
print()
```

### 7. Response metadata (`response.asahi`)

Every completion includes Asahi metadata:

| Field               | Description                          |
|---------------------|--------------------------------------|
| `model_used`        | Model that actually handled the call |
| `cache_hit`         | Whether the result was cached        |
| `cache_tier`        | `"exact"`, `"semantic"`, etc.         |
| `cost_with_asahi`   | Cost with Asahi                      |
| `cost_without_asahi`| Estimated cost without optimization  |
| `savings_usd`       | Dollar savings                       |
| `savings_pct`       | Savings as percentage (0–100)        |
| `routing_reason`    | Why this model was chosen            |

## Environment variables

| Variable        | Purpose                    |
|-----------------|----------------------------|
| `ACORN_API_KEY` | API key (if not passed in) |

## Errors

The SDK raises `acorn.AcornError` subclasses: `AuthenticationError`, `RateLimitError`, `BudgetExceededError`, `APIConnectionError`, `APIError`. Handle them as needed:

```python
from acorn import Acorn, AuthenticationError, RateLimitError

try:
    response = client.chat.completions.create(...)
except AuthenticationError:
    print("Invalid or missing API key")
except RateLimitError:
    print("Rate limited; retry later")
```
