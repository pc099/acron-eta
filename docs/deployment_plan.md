# Asahi Deployment Plan and Tech Stack

> Complete deployment specification covering all environments, infrastructure,
> CI/CD pipelines, and technology dependencies across all 8 phases.
> This is a SaaS product -- every decision targets production readiness.

---

## 1. Environments

### 1.1 Local Development

| Concern | Technology | Notes |
|---------|-----------|-------|
| Runtime | Python 3.10+ (CPython) | Minimum version enforced in `pyproject.toml` |
| API server | Flask 2.3+ with Werkzeug dev server | Auto-reload enabled |
| Cache backend | Python `dict` (in-memory) | Swapped to Redis via adapter in staging/prod |
| Vector DB | In-memory NumPy store | Swapped to Pinecone/Weaviate via adapter |
| Database | SQLite (`asahi.db`) | Swapped to PostgreSQL via adapter |
| Log storage | Local JSONL files (`data/logs/`) | Rotated daily |
| Secrets | `.env` file loaded by `python-dotenv` | Never committed to git |
| Containers | Docker Compose (optional) | Single `docker-compose.dev.yml` for Redis + Postgres |
| Tests | pytest with coverage | `pytest --cov=src --cov-fail-under=90` |

**How to run locally:**

```
# Clone and setup
git clone <repo>
cd asahi
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Configure
cp .env.example .env        # Add API keys

# Validate config
python -m src.config --validate

# Run
python -m src.api            # Starts on http://localhost:5000

# Test
pytest -v --cov=src --cov-fail-under=90
mypy --strict src/
black --check src/
flake8 src/ --max-line-length=100
```

### 1.2 Staging

| Concern | Technology | Notes |
|---------|-----------|-------|
| Runtime | Python 3.10+ in Docker container | Same base image as production |
| API server | Uvicorn 0.24+ behind Gunicorn (4 workers) | ASGI for async provider calls |
| Cache backend | Redis 7.x (single instance) | Persistent RDB snapshots |
| Vector DB | Pinecone (serverless, free tier) | Separate index from production |
| Database | PostgreSQL 15+ (managed, single instance) | Separate database from production |
| Log storage | JSONL to stdout (container logs) | Collected by cloud log agent |
| Secrets | Cloud secret manager (AWS SSM / GCP Secret Manager) | Injected as env vars at container start |
| Containers | Docker with multi-stage build | Builder stage + slim runtime stage |
| CI trigger | Auto-deploy on merge to `staging` branch | Via GitHub Actions |

### 1.3 Production

| Concern | Technology | Notes |
|---------|-----------|-------|
| Runtime | Python 3.10+ in Docker container | Identical image to staging |
| API server | Uvicorn behind Gunicorn (auto-scaled workers) | Worker count = 2 * CPU + 1 |
| Cache backend | Redis Cluster (3+ nodes, replicated) | Persistence: AOF + RDB |
| Vector DB | Pinecone (serverless, production plan) | Dedicated namespace per tenant (Phase 7) |
| Database | PostgreSQL 15+ (managed, HA, read replicas) | Connection pooling via PgBouncer |
| Time-series DB | Prometheus + InfluxDB | Metrics retention: 90 days hot, 1 year cold |
| Event streaming | Kafka (optional, for high-volume tenants) | 3-broker cluster, 7-day retention |
| Log storage | Structured JSON to stdout | Aggregated by Fluentd/Fluent Bit to cloud storage |
| Secrets | Cloud secret manager + Vault (Phase 7) | Auto-rotated API keys |
| Containers | Kubernetes (EKS / GKE / AKS) | Horizontal pod autoscaler |
| CI trigger | Auto-deploy on merge to `main` + manual approval | Blue-green or canary deployment |
| CDN / Load balancer | Cloud ALB / NLB with TLS termination | Health check on `/api/v1/health` |
| DNS | Route53 / Cloud DNS | `api.asahi.dev` (example) |

---

## 2. Tech Stack by Phase

### 2.1 Phase 1: MVP

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Language** | Python | 3.10+ | Core runtime |
| **Web framework** | Flask | >= 2.3 | REST API |
| **Validation** | Pydantic | >= 2.0 | Config and data models |
| **LLM: Anthropic** | anthropic | >= 0.25 | Claude API calls |
| **LLM: OpenAI** | openai | >= 1.0 | GPT API calls |
| **Config** | PyYAML | >= 6.0 | YAML config loading |
| **Env** | python-dotenv | >= 1.0 | `.env` file loading |
| **Testing** | pytest | >= 7.0 | Test runner |
| **Coverage** | pytest-cov | >= 4.0 | Coverage enforcement |
| **Formatting** | black | latest | Code formatting |
| **Linting** | flake8 | latest | Style enforcement |
| **Type checking** | mypy | latest | Static type analysis |
| **Hashing** | hashlib (stdlib) | -- | MD5 cache keys |

### 2.2 Phase 2: Semantic Caching

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Embeddings** | cohere | >= 5.0 | Cohere embed-english-v3.0 |
| **Embeddings (alt)** | openai | >= 1.0 | text-embedding-3-small (fallback) |
| **Vector DB** | pinecone-client | >= 3.0 | Similarity search (serverless) |
| **Vector DB (alt)** | weaviate-client | >= 4.0 | Self-hosted alternative |
| **Numerics** | numpy | >= 1.24 | Vector operations |
| **Similarity** | scipy | >= 1.10 | Cosine similarity |
| **ML utilities** | scikit-learn | >= 1.3 | Threshold tuning |
| **Cache** | redis | >= 5.0 | Distributed Tier 1 cache |
| **Context gen** | anthropic | >= 0.25 | Claude Haiku for context summaries |

### 2.3 Phase 3: Request Batching

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Async** | asyncio (stdlib) | -- | Async batch execution |
| **Async HTTP** | httpx | >= 0.25 | Async provider calls |
| **Queue** | asyncio.Queue / Redis Streams | -- | Request buffering |

### 2.4 Phase 4: Token Optimization

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Tokenizer** | tiktoken | >= 0.5 | OpenAI token counting |
| **Tokenizer** | anthropic (built-in) | -- | Claude token counting |
| **NLP** | spacy (optional) | >= 3.6 | Sentence segmentation for compression |
| **Data** | pandas | >= 2.0 | Benchmark analysis |

### 2.5 Phase 5: Feature Store

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Feature store** | feast | >= 0.35 | Feature serving |
| **Feature store (alt)** | tecton SDK | latest | Enterprise feature store |

### 2.6 Phase 6: Observability

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Metrics** | prometheus-client | >= 0.19 | Instrument code with counters/histograms |
| **Dashboards** | Grafana | >= 10.0 | Dashboard UI (deployed separately) |
| **Logging** | python-json-logger | >= 2.0 | Structured JSON logs |
| **Error tracking** | sentry-sdk | >= 1.40 | Exception capture |
| **Tracing** | opentelemetry-api | >= 1.20 | Distributed tracing |

### 2.7 Phase 7: Enterprise

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Auth** | PyJWT | >= 2.8 | JWT token handling |
| **Auth** | authlib | >= 1.3 | OAuth2 / OIDC / SAML |
| **Encryption** | cryptography | >= 41.0 | AES-256 encryption at rest |
| **ASGI** | uvicorn | >= 0.24 | Production ASGI server |
| **Process mgr** | gunicorn | >= 21.0 | Worker process management |
| **Secrets** | hvac | >= 2.0 | HashiCorp Vault client |
| **Rate limiting** | slowapi or custom | -- | Per-tenant rate limits |

### 2.8 Phase 8: Agent Swarm

| Layer | Package / Tool | Version | Purpose |
|-------|---------------|---------|---------|
| **Orchestration** | Custom (built on Phase 2 components) | -- | Agent workflow engine |
| **Compression** | zlib (stdlib) + custom summarizer | -- | Inter-agent message compression |
| **State** | Redis or PostgreSQL | -- | Agent state persistence |

---

## 3. Infrastructure Architecture

### 3.1 Production Topology

```
                         Internet
                            |
                     ┌──────┴──────┐
                     │  Cloud LB   │
                     │  (TLS 1.3)  │
                     └──────┬──────┘
                            |
              ┌─────────────┼─────────────┐
              |             |             |
        ┌─────┴─────┐ ┌────┴─────┐ ┌────┴─────┐
        │  Asahi    │ │  Asahi   │ │  Asahi   │
        │  Pod 1   │ │  Pod 2   │ │  Pod N   │
        │  (API +  │ │  (API +  │ │  (API +  │
        │  Worker) │ │  Worker) │ │  Worker) │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             |             |             |
             └─────────────┼─────────────┘
                           |
          ┌────────────────┼────────────────┐
          |                |                |
    ┌─────┴─────┐  ┌──────┴──────┐  ┌─────┴─────┐
    │  Redis    │  │ PostgreSQL  │  │ Pinecone  │
    │  Cluster  │  │   (HA)     │  │ (Managed) │
    │ (Cache)   │  │ (Metadata) │  │ (Vectors) │
    └───────────┘  └─────────────┘  └───────────┘
          |                |
    ┌─────┴─────┐  ┌──────┴──────┐
    │ Prometheus │  │   Kafka     │
    │ + Grafana  │  │ (Optional)  │
    └───────────┘  └─────────────┘
```

### 3.2 Resource Requirements

| Component | CPU | Memory | Storage | Instances |
|-----------|-----|--------|---------|-----------|
| Asahi API pod | 1 vCPU | 2 GB | -- | 2-20 (HPA) |
| Redis Cluster | 2 vCPU | 4 GB | 20 GB SSD | 3 (primary + 2 replicas) |
| PostgreSQL | 2 vCPU | 4 GB | 50 GB SSD | 1 primary + 1 read replica |
| Prometheus | 1 vCPU | 2 GB | 100 GB SSD | 1 |
| Grafana | 0.5 vCPU | 1 GB | 10 GB | 1 |
| Kafka (optional) | 2 vCPU | 4 GB | 100 GB SSD | 3 brokers |

### 3.3 Scaling Strategy

| Component | Scaling Method | Trigger |
|-----------|---------------|---------|
| API pods | Horizontal Pod Autoscaler | CPU > 70% or request queue > 100 |
| Redis | Add read replicas | Cache hit latency > 5 ms p99 |
| PostgreSQL | Read replicas + connection pooling | Query latency > 50 ms p99 |
| Pinecone | Managed auto-scaling | Handled by Pinecone serverless |

**Performance targets:**

| Metric | Target |
|--------|--------|
| Throughput | 10,000 requests/second |
| Cache lookup latency (p99) | < 5 ms |
| End-to-end latency (p99, excl. LLM) | < 50 ms |
| Asahi overhead per request | < $0.001 |
| Availability | 99.9% uptime |

---

## 4. CI/CD Pipeline

### 4.1 Pipeline Stages

```
Commit
  │
  ├─ Stage 1: Lint + Type Check (parallel)
  │    ├─ black --check src/
  │    ├─ flake8 src/ --max-line-length=100
  │    └─ mypy --strict src/
  │
  ├─ Stage 2: Unit Tests
  │    └─ pytest tests/unit/ -v --cov=src --cov-fail-under=90
  │
  ├─ Stage 3: Integration Tests (if RUN_INTEGRATION_TESTS=true)
  │    └─ pytest tests/integration/ -v (uses Docker services)
  │
  ├─ Stage 4: Build Docker Image
  │    └─ docker build --target production -t asahi:$SHA .
  │
  ├─ Stage 5: Security Scan
  │    ├─ pip-audit (dependency vulnerabilities)
  │    ├─ bandit -r src/ (static security analysis)
  │    └─ trivy image asahi:$SHA (container scan)
  │
  ├─ Stage 6: Push Image
  │    └─ docker push <registry>/asahi:$SHA
  │
  ├─ Stage 7: Deploy to Staging (auto on staging branch)
  │    └─ kubectl set image deployment/asahi asahi=<registry>/asahi:$SHA
  │
  ├─ Stage 8: Smoke Tests on Staging
  │    ├─ /api/v1/health returns healthy
  │    ├─ /api/v1/infer returns valid response (test prompt)
  │    └─ /api/v1/metrics returns valid aggregates
  │
  └─ Stage 9: Deploy to Production (manual approval on main)
       └─ Blue-green or canary rollout via Kubernetes
```

### 4.2 GitHub Actions Workflow Structure

```
.github/
  workflows/
    ci.yml                # Stages 1-3 on every PR
    build-and-push.yml    # Stages 4-6 on merge to staging/main
    deploy-staging.yml    # Stage 7-8 on merge to staging
    deploy-production.yml # Stage 9 on merge to main (manual gate)
```

### 4.3 Branch Strategy

| Branch | Purpose | Deploy Target |
|--------|---------|---------------|
| `main` | Production-ready code | Production (with approval) |
| `staging` | Pre-production validation | Staging (auto) |
| `feat/*` | Feature development | None (CI only) |
| `fix/*` | Bug fixes | None (CI only) |
| `release/vX.Y.Z` | Release candidate | Staging then production |

---

## 5. Docker Configuration

### 5.1 Multi-Stage Dockerfile

```dockerfile
# Stage 1: Builder
FROM python:3.10-slim AS builder
WORKDIR /app
COPY pyproject.toml setup.cfg ./
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Production
FROM python:3.10-slim AS production
WORKDIR /app

# Non-root user
RUN groupadd -r asahi && useradd -r -g asahi asahi

COPY --from=builder /install /usr/local
COPY src/ src/
COPY config/ config/

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/api/v1/health')"

USER asahi
EXPOSE 5000

CMD ["gunicorn", "src.api:create_app()", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

### 5.2 Docker Compose (Local Development)

```yaml
# docker-compose.dev.yml
version: "3.9"

services:
  asahi:
    build:
      context: .
      target: production
    ports:
      - "5000:5000"
    env_file: .env
    depends_on:
      - redis
      - postgres
    environment:
      - REDIS_URL=redis://redis:6379
      - DATABASE_URL=postgresql://asahi:asahi@postgres:5432/asahi

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_USER: asahi
      POSTGRES_PASSWORD: asahi
      POSTGRES_DB: asahi
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## 6. Kubernetes Configuration (Production)

### 6.1 Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: asahi-api
  labels:
    app: asahi
    component: api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: asahi
  template:
    metadata:
      labels:
        app: asahi
        component: api
    spec:
      containers:
        - name: asahi
          image: <registry>/asahi:latest
          ports:
            - containerPort: 5000
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: 1000m
              memory: 2Gi
          readinessProbe:
            httpGet:
              path: /api/v1/health
              port: 5000
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: 5000
            initialDelaySeconds: 30
            periodSeconds: 30
          envFrom:
            - secretRef:
                name: asahi-secrets
            - configMapRef:
                name: asahi-config
```

### 6.2 Horizontal Pod Autoscaler

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: asahi-api-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: asahi-api
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

### 6.3 Service and Ingress

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: asahi-api
spec:
  selector:
    app: asahi
  ports:
    - port: 80
      targetPort: 5000
  type: ClusterIP
---
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: asahi-ingress
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
    - hosts:
        - api.asahi.dev
      secretName: asahi-tls
  rules:
    - host: api.asahi.dev
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: asahi-api
                port:
                  number: 80
```

---

## 7. Database Migrations

| Tool | Version | Purpose |
|------|---------|---------|
| Alembic | >= 1.12 | PostgreSQL schema migrations |

Migration strategy:
- All schema changes via Alembic migration scripts.
- Migrations run automatically on deploy (pre-start hook).
- Backward-compatible migrations only (no destructive changes without a two-phase rollout).
- Migration scripts tested in CI against a fresh database.

---

## 8. Monitoring and Alerting Stack

### 8.1 Metrics Collection

| Metric | Type | Source | Alert Threshold |
|--------|------|--------|-----------------|
| `asahi_requests_total` | Counter | API middleware | -- |
| `asahi_request_latency_seconds` | Histogram | API middleware | p95 > 2x rolling avg |
| `asahi_cache_hits_total` | Counter (by tier) | Cache layer | hit_rate < 10% over 1 hour |
| `asahi_cost_dollars_total` | Counter (by model) | Cost calculator | daily > 2x 7-day avg |
| `asahi_errors_total` | Counter (by type) | Error handler | rate > 1% of requests |
| `asahi_model_latency_seconds` | Histogram (by model) | Provider adapter | p95 > 5s |
| `asahi_active_requests` | Gauge | API middleware | > 80% of capacity |

### 8.2 Dashboard Layout (Grafana)

| Panel | Visualisation | Data Source |
|-------|---------------|-------------|
| Request rate | Time-series line | `rate(asahi_requests_total[5m])` |
| Latency percentiles | Time-series (p50, p95, p99) | `histogram_quantile(...)` |
| Cache hit rate by tier | Stacked area | `rate(asahi_cache_hits_total[5m])` |
| Cost per hour | Time-series | `increase(asahi_cost_dollars_total[1h])` |
| Model usage distribution | Pie chart | `sum by (model) (asahi_requests_total)` |
| Error rate | Time-series | `rate(asahi_errors_total[5m])` |
| Active pods | Gauge | Kubernetes metrics |

### 8.3 On-Call Alerting

| Severity | Channel | Response Time |
|----------|---------|--------------|
| Critical (all providers down, data loss) | PagerDuty / Opsgenie | 15 min |
| High (cost spike, error rate > 5%) | Slack #asahi-alerts | 1 hour |
| Medium (cache hit regression, latency drift) | Slack #asahi-ops | 4 hours |
| Low (token estimation drift, config warnings) | Daily digest email | Next business day |

---

## 9. Security Checklist (Progressive by Phase)

### Phase 1-2

- [ ] All secrets in environment variables, never in code or config files
- [ ] `.env` in `.gitignore`
- [ ] HTTPS enforced (TLS 1.3) on all non-local environments
- [ ] Dependency vulnerability scanning in CI (`pip-audit`)
- [ ] Static security analysis in CI (`bandit`)
- [ ] Container image scanning (`trivy`)
- [ ] Non-root container user

### Phase 6-7

- [ ] API key authentication on all endpoints
- [ ] Rate limiting per tenant (configurable)
- [ ] RBAC enforced on management endpoints
- [ ] Encryption at rest (AES-256) for sensitive data
- [ ] Audit logging on all write operations
- [ ] PII detection and masking in logs
- [ ] SOC 2 Type II controls implemented
- [ ] HIPAA BAA support (if healthcare tenants)
- [ ] GDPR data subject rights endpoints
- [ ] Penetration testing completed

---

## 10. Disaster Recovery

| Scenario | Recovery Strategy | RTO | RPO |
|----------|------------------|-----|-----|
| Single pod failure | Kubernetes auto-restart | < 30s | 0 |
| Redis node failure | Cluster failover | < 1 min | 0 (replicated) |
| PostgreSQL failure | Managed failover to replica | < 5 min | < 1 min |
| Full region outage | Multi-region failover (Phase 7+) | < 15 min | < 5 min |
| Pinecone outage | Degrade to Tier 1 caching only | Immediate | N/A |
| LLM provider outage | Automatic fallback to alt provider | Immediate | 0 |

**Backup Schedule:**

| Data Store | Method | Frequency | Retention |
|------------|--------|-----------|-----------|
| PostgreSQL | Automated managed snapshots | Every 6 hours | 30 days |
| Redis | RDB snapshot + AOF | Every 1 hour | 7 days |
| Event logs | Archive to cloud object storage | Daily | 1 year |
| Config files | Git repository | On every change | Indefinite |

---

## 11. Cost Estimates (Infrastructure)

### 11.1 Staging Environment (Monthly)

| Service | Estimate |
|---------|----------|
| Compute (2 small instances) | $40 |
| Redis (single node) | $15 |
| PostgreSQL (small managed) | $25 |
| Pinecone (free tier) | $0 |
| Container registry | $5 |
| **Total** | **~$85/month** |

### 11.2 Production Environment (Monthly, baseline)

| Service | Estimate |
|---------|----------|
| Compute (3 pods, auto-scale to 10) | $150-500 |
| Redis Cluster (3 nodes) | $90 |
| PostgreSQL (HA, managed) | $120 |
| Pinecone (standard plan) | $70 |
| Prometheus + Grafana | $30 |
| Load balancer + TLS | $20 |
| Cloud storage (logs) | $10 |
| Kafka (optional, 3 brokers) | $180 |
| **Total (without Kafka)** | **~$490/month** |
| **Total (with Kafka)** | **~$670/month** |

These costs scale with request volume. At 10,000+ req/day the LLM API costs
($100-500/month with Asahi optimisation) will dwarf infrastructure costs.

---

## 12. Release Checklist (Every Deployment)

### Pre-Deploy

- [ ] All CI stages green (lint, type check, tests, security scan)
- [ ] Docker image built and pushed to registry
- [ ] Database migrations tested against staging
- [ ] Changelog updated in `CHANGELOG.md`
- [ ] Version bumped in `pyproject.toml` and `config.yaml`

### Deploy

- [ ] Deploy to staging and run smoke tests
- [ ] Verify `/health` returns healthy with correct version
- [ ] Verify `/infer` returns correct response (test prompt)
- [ ] Verify `/metrics` returns sane values
- [ ] Monitor error rate for 15 minutes
- [ ] Deploy to production (manual approval)
- [ ] Monitor error rate and latency for 30 minutes
- [ ] Verify Grafana dashboards show healthy metrics

### Post-Deploy

- [ ] Confirm no error rate increase
- [ ] Confirm no latency regression
- [ ] Confirm cache hit rate stable
- [ ] Update deployment log with version and timestamp
- [ ] Notify team in Slack

---

## 13. Dependency Management

**Policy:**
- Pin major and minor versions in `pyproject.toml` (e.g., `flask >= 2.3, < 3.0`).
- Run `pip-audit` weekly to catch new CVEs.
- Dependabot or Renovate for automated dependency PRs.
- No dependency added without explicit justification in the PR.

**Lock file:**
- `requirements.txt` generated from `pip-compile` for reproducible builds.
- Lock file committed to git and updated only via CI.
