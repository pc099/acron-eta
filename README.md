# ASAHIO — LLM Agent Control Plane

**ASAHIO** is an enterprise-grade observability, reliability, and intelligent routing platform for the agent economy. It sits between your agents and LLMs, providing real-time routing, semantic caching, hallucination detection, and autonomous intervention.

[![PyPI version](https://badge.fury.io/py/asahio.svg)](https://badge.fury.io/py/asahio)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Live Demo:** [app.asahio.dev](https://app.asahio.dev)
**Documentation:** [docs.asahio.dev](https://docs.asahio.dev)
**SDK:** [pypi.org/project/asahio](https://pypi.org/project/asahio/)

---

## Why ASAHIO?

LLM infrastructure is a black box. You can't see what your agents are doing, you can't control their behavior, and you can't prevent hallucinations or cost overruns. ASAHIO turns that black box into a controllable, observable system.

**Core Value Proposition:**
- ✅ **See everything** — Every LLM call traced, graphed, and risk-scored
- ✅ **Route intelligently** — 6-factor engine picks the best model for each call
- ✅ **Cache semantically** — Redis + Pinecone two-tier cache (85%+ hit rate)
- ✅ **Detect hallucinations** — Real-time confidence calibration and fact-checking
- ✅ **Intervene safely** — Autonomous mode can block or reroute risky calls
- ✅ **Self-host ready** — HIPAA-compliant on-prem deployment available

---

## Features

### 🎯 Two-Dimensional Mode System

ASAHIO decouples **routing** (how a model is selected) from **intervention** (how ASAHIO acts):

**Routing Modes:**
- **AUTO** — 6-factor engine: complexity, context length, ABA history, latency, budget, provider health
- **EXPLICIT** — Pin to a specific model, fine-tuned endpoint, or custom vLLM/Ollama instance
- **GUIDED** — Customer rules: cost ceiling, provider allowlist, step-based routing, fallback chains

**Intervention Modes:**
- **OBSERVE** — Watch only, never modify calls
- **ASSISTED** — Cache hits, augment risky prompts, reroute on high risk
- **AUTONOMOUS** — Full intervention including blocking (requires explicit authorization)

All 9 combinations (3 routing × 3 intervention) are valid and independent.

### 🧠 Agent Behavioral Analytics (ABA)

ASAHIO learns your agents' behavioral patterns over time:
- Complexity distribution, output type, hallucination rate
- Model C global knowledge pool (anonymized cross-org priors)
- Cold-start routing for new agents
- Mode transition recommendations (OBSERVE → ASSISTED → AUTONOMOUS)

### 🔍 Observability & Tracing

- **Session graphs** — Visualize multi-step agent conversations with dependency tracking
- **Live traces** — WebSocket streaming for real-time call visibility
- **Risk scoring** — <2ms sync risk estimate on every call
- **Intervention logs** — Immutable audit trail of every ASAHIO decision

### 💾 Semantic Cache

Two-tier architecture for maximum hit rate:
- **Tier 1 (Redis)** — Exact match, ~0.5ms lookup
- **Tier 2 (Pinecone)** — Semantic similarity with Cohere embeddings, ~20ms lookup
- **Promotion logic** — Semantic hits above 0.95 similarity auto-promote to exact cache
- **Context-aware keys** — Dependency fingerprint prevents invalid cache hits

### 🔐 Enterprise Ready

- **Multi-tenancy** — Organisation-level isolation, cross-org returns 404 (not 403)
- **RBAC** — OWNER, ADMIN, MEMBER, VIEWER roles with endpoint-level scopes
- **Audit logging** — Immutable hash chain for tamper detection
- **Encryption at rest** — Fernet-encrypted BYOK provider keys
- **Compliance tiers** — STANDARD, ENTERPRISE, HIPAA (separate Pinecone indexes)

### 🚀 Bring Your Own Model (BYOM)

- Ollama self-hosted instances
- Fine-tuned endpoints (OpenAI, Anthropic)
- Custom vLLM/TGI/local endpoints
- Fallback chains with circuit breakers

---

## Quick Start

### Install SDK

```bash
pip install asahio
```

### Basic Usage

```python
from asahio import Asahio

client = Asahio(api_key="asahio_live_...")

# Simple completion with AUTO routing
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "What is quantum computing?"}],
    model="gpt-4o",  # Requested model (may be overridden by routing)
)

print(response.choices[0].message.content)

# Check what actually happened
print(f"Model used: {response.asahio.model_used}")
print(f"Provider: {response.asahio.provider}")
print(f"Cache hit: {response.asahio.cache_hit}")
print(f"Cost: ${response.asahio.cost_with_asahio:.4f}")
print(f"Saved: ${response.asahio.cost_without_asahio - response.asahio.cost_with_asahio:.4f}")
```

### Advanced: Agent with Session Tracking

```python
from asahio import Asahio

client = Asahio(api_key="asahio_live_...")

# Create an agent
agent = client.agents.create(
    name="Customer Support Bot",
    routing_mode="AUTO",
    intervention_mode="ASSISTED",
)

# Create a session for multi-turn conversation
session = client.agents.create_session(
    agent_id=agent.id,
    external_session_id="user-12345-session-1"
)

# Make calls with agent + session context
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "I need help with my order"}],
    agent_id=agent.id,
    session_id=session.external_session_id,
)

# View session graph (all steps with dependencies)
graph = client.traces.get_session_graph(session_id=session.id)
print(f"Total steps: {graph.step_count}")
for step in graph.steps:
    print(f"  Step {step.step_number}: {step.model_used} ({step.latency_ms}ms)")
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         ASAHIO Gateway                          │
│                    POST /v1/chat/completions                    │
└────────────┬────────────────────────────────────────────────────┘
             │
   ┌─────────▼──────────┐
   │  AuthMiddleware    │  API Key → org_id, plan, scopes
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  RateLimiter       │  Monthly request/token/budget limits
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Risk Scorer       │  <2ms sync risk estimate
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Cache Lookup      │  Redis exact → Pinecone semantic
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Routing Engine    │  6-factor AUTO / EXPLICIT / GUIDED
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Circuit Breaker   │  Per-provider failure detection
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Provider Call     │  OpenAI, Anthropic, Ollama, vLLM, etc.
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Response Builder  │  Assemble ChatCompletion + .asahio metadata
   └─────────┬──────────┘
             │
   ┌─────────▼──────────┐
   │  Fire-and-Forget   │  async trace write, ABA observation, cache store
   └────────────────────┘
```

**Never blocks the critical path:** Trace writing, ABA updates, and intervention logging all run as `asyncio.create_task()` after the response is returned.

---

## Dashboard

ASAHIO includes a full Next.js dashboard at [app.asahio.dev](https://app.asahio.dev):

- **Agent Registry** — Create, configure, and monitor agents
- **Live Traces** — Real-time WebSocket streaming of LLM calls
- **Session Graphs** — Visualize multi-step conversations with dependency trees
- **Routing Decisions** — Audit trail of every routing choice with factor breakdown
- **Intervention Timeline** — When, why, and how ASAHIO intervened
- **Mode Transitions** — OBSERVE → ASSISTED → AUTONOMOUS progression
- **Fleet Overview** — Cross-agent mode distribution and intervention summary
- **Hallucination Tagging** — Human-in-the-loop feedback for ABA engine
- **BYOM Management** — Register Ollama instances, fine-tuned endpoints, fallback chains
- **Analytics** — Cost breakdown, cache performance, latency percentiles

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| **Gateway** |
| `/v1/chat/completions` | POST | OpenAI-compatible chat completions (main entry point) |
| **Agents** |
| `/agents` | GET | List all agents for org |
| `/agents` | POST | Create new agent |
| `/agents/{id}` | GET/PATCH | Get or update agent |
| `/agents/{id}/stats` | GET | Agent statistics (calls, cache hit rate, etc.) |
| `/agents/{id}/mode-eligibility` | GET | Check if eligible for mode transition |
| `/agents/{id}/mode-transition` | POST | Transition to new mode |
| `/agents/{id}/sessions` | POST | Create session for multi-turn tracking |
| **Traces** |
| `/traces/traces` | GET | List call traces with filters |
| `/traces/traces/{id}` | GET | Get single trace |
| `/traces/sessions` | GET | List sessions |
| `/traces/sessions/{id}` | GET | Get session details |
| `/traces/sessions/{id}/graph` | GET | Get session dependency graph |
| **Routing** |
| `/routing/decisions` | GET | List routing decisions |
| `/routing/decisions/{id}` | GET | Get single decision with factor breakdown |
| `/routing/constraints` | GET/POST | Manage GUIDED routing rules |
| **Interventions** |
| `/interventions/logs` | GET | List intervention logs |
| `/interventions/stats` | GET | Intervention stats by level |
| `/interventions/fleet-overview` | GET | Fleet-wide mode distribution |
| **ABA** |
| `/aba/fingerprints` | GET | List agent behavioral fingerprints |
| `/aba/fingerprints/{agent_id}` | GET | Get single agent fingerprint |
| `/aba/calls/{call_id}/tag` | POST | Tag hallucination (human feedback) |
| **Providers** |
| `/providers/keys` | GET/POST/DELETE | BYOK provider key management |
| `/providers/ollama/verify` | POST | Verify Ollama instance connectivity |
| `/providers/ollama` | GET | List Ollama configs |
| `/providers/chains` | GET/POST/DELETE | Fallback chain management |
| `/providers/chains/{id}/test` | POST | Dry-run chain (verify all keys available) |
| **Models** |
| `/models` | GET | List registered model profiles |
| `/models/endpoints` | GET/POST | Manage BYOM endpoints |
| **Health** |
| `/health` | GET | Service health + component status |

Full API documentation available at `/docs` (Swagger UI).

---

## Environment Variables

### Backend

| Variable | Required | Description |
|----------|----------|-------------|
| `DATABASE_URL` | Yes | PostgreSQL connection URL |
| `REDIS_URL` | Yes | Redis connection URL (cache + session state) |
| `PINECONE_API_KEY` | Yes | Pinecone API key (vector cache) |
| `PINECONE_HOST` | Production | Pinecone host (skips describe_index call) |
| `COHERE_API_KEY` | Yes | Cohere API key (production embeddings) |
| `CLERK_SECRET_KEY` | Yes | Clerk secret key (JWT verification) |
| `CLERK_PUBLISHABLE_KEY` | Yes | Clerk publishable key |
| `FERNET_KEY` | Yes | Base64-encoded encryption key for BYOK secrets |
| `OPENAI_API_KEY` | Optional | Default OpenAI key (fallback if no BYOK) |
| `ANTHROPIC_API_KEY` | Optional | Default Anthropic key (fallback if no BYOK) |
| `STRIPE_SECRET_KEY` | Optional | Stripe secret key (billing) |
| `ENVIRONMENT` | Optional | `development`, `staging`, `production` |

### Frontend

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key |
| `CLERK_SECRET_KEY` | Clerk secret key (server-side) |
| `NEXT_PUBLIC_API_URL` | ASAHIO backend URL (default: `https://api.asahio.dev`) |

---

## Deployment

### Railway (Backend)

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login and deploy
railway login
railway up
```

**Services needed:**
- PostgreSQL (Railway managed)
- Redis (Railway managed)
- Backend (this repo)

**Environment variables:** Set all variables listed above in Railway dashboard.

**Pre-deploy migration:** Railway runs `python scripts/bootstrap_alembic.py` before startup (see `railway.toml`).

### Vercel (Frontend)

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
cd frontend
vercel --prod
```

**Environment variables:** Set `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`, `NEXT_PUBLIC_API_URL`.

---

## Self-Hosted Deployment

ASAHIO supports fully on-premise deployment for HIPAA compliance and air-gapped environments.

**Included:**
- Docker Compose template
- Local embeddings (Sentence Transformers, no Cohere)
- Local vector store (Qdrant or LanceDB, no Pinecone)
- Internal OIDC/LDAP integration (no Clerk)
- BYOM only (Ollama, vLLM, TGI)

**Contact:** [enterprise@asahio.dev](mailto:enterprise@asahio.dev)

---

## SDK

### Installation

```bash
pip install asahio
```

### Features

- ✅ OpenAI-compatible `chat.completions.create()` interface
- ✅ Streaming support
- ✅ Agent and session management
- ✅ Trace and intervention querying
- ✅ BYOM endpoint registration
- ✅ Typed responses with full `.asahio` metadata
- ✅ Async support (`AsyncAsahio`)
- ✅ Backward compatibility (`asahi`, `acorn` package aliases)

### Example: Streaming

```python
from asahio import Asahio

client = Asahio(api_key="asahio_live_...")

stream = client.chat.completions.create(
    messages=[{"role": "user", "content": "Count to 10"}],
    stream=True,
)

for chunk in stream:
    print(chunk.choices[0].delta.content, end="", flush=True)
```

---

## Project Structure

```
asahio/
├── backend/
│   ├── app/
│   │   ├── api/              16 routers (gateway, agents, traces, etc.)
│   │   ├── core/             Routing engine + intervention + optimizer
│   │   ├── db/               21 ORM models + Alembic migrations
│   │   ├── services/         26 service files (ABA, cache, risk, etc.)
│   │   ├── schemas/          Pydantic request/response types
│   │   └── middleware/       Auth, CORS, rate limiting, RBAC, audit
│   ├── alembic/              Database migrations (7 files)
│   ├── tests/                41 test files, 501+ tests
│   └── scripts/              Bootstrap, smoke tests
├── frontend/
│   ├── app/
│   │   └── (dashboard)/[orgSlug]/  19 dashboard sections
│   ├── components/           Reusable UI (charts, tables, badges)
│   └── lib/                  api.ts (typed client), utils.ts
├── sdk/
│   ├── src/asahio/           Canonical Python SDK
│   ├── src/asahi/            Backward-compat alias
│   ├── src/acorn/            Backward-compat alias
│   └── tests/                SDK integration tests
└── docs/                     Engineering roadmap, compliance docs
```

---

## Development

### Backend Tests

```bash
cd backend
pytest tests/ -v --ignore=tests/test_gateway.py  # ~35s, 501+ tests
pytest tests/test_agents.py -v                    # Single module
```

### Frontend Dev

```bash
cd frontend
npm install
npm run dev  # http://localhost:3000
```

### Build SDK

```bash
cd sdk
python -m build
pip install dist/asahio-0.2.2-py3-none-any.whl
```

---

## Roadmap

See [docs/NEXT_STEPS.md](docs/NEXT_STEPS.md) for the full prioritized backlog.

**Next priorities (P2):**
- Sentry error tracking
- Cloudflare WAF integration
- PostgreSQL RLS policies
- HMAC request signing
- Load testing (1000+ agents, 10k RPS)
- Separate Model C Pinecone index

**Future (P3):**
- OpenTelemetry distributed tracing
- HIPAA Docker Compose template
- MFA enforcement
- Zero-downtime deploys
- Penetration testing

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Before submitting a PR:**
1. Run tests: `pytest tests/ -v`
2. Format code: `black backend/ sdk/`
3. Lint: `ruff check backend/ sdk/`
4. Update SDK types if you change API response shapes

---

## Support

- **Documentation:** [docs.asahio.dev](https://docs.asahio.dev)
- **Issues:** [github.com/asahio-ai/asahio/issues](https://github.com/asahio-ai/asahio/issues)
- **Email:** [support@asahio.dev](mailto:support@asahio.dev)
- **Enterprise:** [enterprise@asahio.dev](mailto:enterprise@asahio.dev)

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

Built with:
- [FastAPI](https://fastapi.tiangolo.com/) — Backend framework
- [Next.js](https://nextjs.org/) — Frontend framework
- [Pinecone](https://www.pinecone.io/) — Vector database
- [Cohere](https://cohere.ai/) — Embeddings
- [Clerk](https://clerk.com/) — Authentication
- [Railway](https://railway.app/) — Backend hosting
- [Vercel](https://vercel.com/) — Frontend hosting

---

**Made with ❤️ by the ASAHIO team**
