# Quick start

Get an API key and run your first request in under five minutes.

## 1. Get an API key

**Option A — Self-serve signup** (when the API has `DATABASE_URL` configured):

```bash
curl -X POST https://your-asahi-api.com/signup \
  -H "Content-Type: application/json" \
  -d '{"org_name": "My Company", "user_id": "dev1", "email": "you@example.com"}'
```

Response includes `api_key` (store it securely; it is shown only once) and `org_id`.

**Option B — Admin-created key:** Ask your admin to create a key via `POST /governance/api-keys` (with `X-Admin-Secret` or admin scope). You receive `api_key`, `org_id`, `user_id`.

## 2. Set base URL and auth

Use your Asahi API base URL (e.g. `https://your-asahi-api.com`) and the API key from step 1.

- **curl:** set header `Authorization: Bearer YOUR_API_KEY`.
- **OpenAI SDK:** set `base_url` to your Asahi URL and use the key as `api_key`; then call `client.chat.completions.create(...)` as usual — Asahi exposes `POST /v1/chat/completions`.

## 3. First request

**curl (native Asahi endpoint):**

```bash
curl -X POST https://your-asahi-api.com/infer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{"prompt": "What is Python?", "routing_mode": "autopilot"}'
```

**Python (OpenAI-compatible):**

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://your-asahi-api.com/v1",  # Asahi base URL + /v1
    api_key="YOUR_API_KEY",
)
resp = client.chat.completions.create(
    model="asahi",  # or a specific model for explicit routing
    messages=[{"role": "user", "content": "What is Python?"}],
    max_tokens=256,
)
print(resp.choices[0].message.content)
```

**Python (native Asahi `/infer`):**

```python
import requests

r = requests.post(
    "https://your-asahi-api.com/infer",
    headers={"Authorization": "Bearer YOUR_API_KEY", "Content-Type": "application/json"},
    json={"prompt": "What is Python?", "routing_mode": "autopilot"},
)
print(r.json()["response"], r.json()["cost"], r.json()["model_used"])
```

## Next steps

- **API reference:** [API_CONTRACT.md](API_CONTRACT.md) and interactive docs at `/docs`, OpenAPI at `/openapi.json`.
- **Integration guide:** [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for step-by-step integration and routing modes.
- **Local run:** [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md) for running and testing Asahi locally.
