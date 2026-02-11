# Asahi SaaS Production Readiness Checklist

> **Purpose:** Use this master checklist before releasing any phase to clients. Each phase doc has phase-specific items; this template is the global bar for production-quality SaaS.

---

## Code Quality

- [ ] **Type hints** on every function (see [QUALITY_STANDARDS.md](QUALITY_STANDARDS.md))
- [ ] **Docstrings** on every public class and function
- [ ] **No hardcoded values**; config-driven (env, YAML, DB)
- [ ] **Error handling** on all external calls (APIs, DB, cache)
- [ ] **Logging** structured (JSON); no PII in logs
- [ ] **Linting** clean: black, flake8, mypy
- [ ] **Tests** > 90% coverage on critical paths
- [ ] **No magic numbers**; use named constants
- [ ] **Functions < 50 lines**; split if larger

---

## Security

- [ ] **Authentication** on all APIs (API key, OAuth, or SSO)
- [ ] **No secrets in code**; env vars or vault
- [ ] **TLS 1.3+** for all network traffic
- [ ] **Input validation** on all request fields
- [ ] **Output sanitization** where needed
- [ ] **Rate limiting** per tenant/key
- [ ] **RBAC** enforced on sensitive operations (Phase 7+)
- [ ] **Audit logging** on config/mutation (Phase 7+)

---

## Reliability

- [ ] **Health check** includes dependency status
- [ ] **Graceful degradation** when dependencies fail
- [ ] **Retry + backoff** on transient failures
- [ ] **Circuit breaker** for failing external services (where applicable)
- [ ] **Timeouts** on all external calls
- [ ] **Idempotency** where required (e.g. billing)
- [ ] **Crash recovery** (queue persistence, state recovery)

---

## Observability

- [ ] **Metrics** exported (Prometheus, StatsD)
- [ ] **Tracing** for request flow (optional)
- [ ] **Alerts** on error rate, latency, cost spike
- [ ] **Dashboards** for ops
- [ ] **Log aggregation** compatible
- [ ] **Request ID** in logs and responses for support

---

## Scalability

- [ ] **Stateless** where possible
- [ ] **Cache** for hot data (Redis, etc.)
- [ ] **Connection pooling** for DB/cache
- [ ] **Horizontal scaling** documented and tested
- [ ] **Cardinality limits** on metrics/labels
- [ ] **Backpressure** when overloaded (queue full, 429)

---

## Multi-Tenancy

- [ ] **Tenant isolation** (org_id, namespace)
- [ ] **Per-tenant quotas** (rate, budget)
- [ ] **Per-tenant config** (policies, features)
- [ ] **No cross-tenant data** in logs/metrics

---

## Compliance & Data

- [ ] **Data retention** policy documented
- [ ] **PII handling** documented; redaction where required
- [ ] **GDPR** readiness (access, deletion, consent)
- [ ] **HIPAA** readiness if targeting healthcare
- [ ] **SOC 2** prep if targeting enterprise
- [ ] **Encryption at rest** for sensitive data

---

## Documentation

- [ ] **README** with setup, env vars, run instructions
- [ ] **API docs** (OpenAPI/Swagger)
- [ ] **Architecture diagram** and component overview
- [ ] **Runbook** for common ops tasks
- [ ] **Changelog** for releases

---

## Deployment

- [ ] **Docker image** buildable and runnable
- [ ] **Environment parity** (dev/staging/prod)
- [ ] **Secrets management** (vault, parameter store)
- [ ] **CI/CD** pipeline for tests and deploy
- [ ] **Rollback** procedure documented
- [ ] **Disaster recovery** plan

---

## Client Readiness

- [ ] **Backward compatibility** documented
- [ ] **Breaking changes** in changelog
- [ ] **Migration guide** if upgrading
- [ ] **SLAs** documented (uptime, latency)
- [ ] **Support** process (tickets, escalation)
- [ ] **Billing** integration if applicable

---

## Phase-Specific Checklists

Refer to each phase doc for phase-specific items:

- [Phase 1](phase1_requirements.md#phase-1-production-readiness-checklist)
- [Phase 2](phase2_requirements.md#phase-2-production-readiness-checklist)
- [Phase 3](phase3_requirements.md#phase-3-production-readiness-checklist)
- [Phase 4](phase4_requirements.md#phase-4-production-readiness-checklist)
- [Phase 5](phase5_requirements.md#phase-5-production-readiness-checklist)
- [Phase 6](phase6_requirements.md#phase-6-production-readiness-checklist)
- [Phase 7](phase7_requirements.md#phase-7-production-readiness-checklist)
- [Phase 8](phase8_requirements.md#phase-8-production-readiness-checklist)
