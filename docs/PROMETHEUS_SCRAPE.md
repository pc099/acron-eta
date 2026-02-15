# Prometheus scrape and structured logging

## Prometheus metrics

Asahi exposes metrics in Prometheus text exposition format on two endpoints:

| Endpoint | Purpose |
|----------|---------|
| `GET /metrics` | Primary metrics (cost, cache, latency, requests, uptime). Same format as `/analytics/prometheus`. |
| `GET /analytics/prometheus` | Same content; use when you want analytics scope or a separate path. |

Both return `text/plain; version=0.0.4; charset=utf-8` with counters, gauges, and histograms (e.g. latency, tokens, cache hits by tier).

### Example scrape config

Add to your Prometheus `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: asahi
    metrics_path: /metrics
    static_configs:
      - targets: ['asahi-api:8000']   # or localhost:8000 for local
    scrape_interval: 15s
    scrape_timeout: 10s
```

If the API is behind auth, configure `authorization` or `bearer_token` in the scrape config, or use a dedicated metrics endpoint that does not require an API key (e.g. allowlist `/metrics` in your auth layer).

### Optional: alerting rules

Example rules (save as `asahi_alerts.yml` and include in Prometheus):

```yaml
groups:
  - name: asahi
    rules:
      - alert: AsahiDown
        expr: up{job="asahi"} == 0
        for: 1m
        labels: { severity: critical }
        annotations:
          summary: "Asahi API is down"

      - alert: AsahiHighErrorRate
        expr: rate(asahi_requests_total{status=~"5.."}[5m]) / rate(asahi_requests_total[5m]) > 0.05
        for: 5m
        labels: { severity: warning }
        annotations:
          summary: "Asahi error rate above 5%"
```

Adjust metric names to match what `MetricsCollector.get_prometheus_metrics()` actually exports (e.g. `asahi_requests_total` or the names used in your metrics module).

## Structured logging

Inference and auth flows log with structured `extra` fields so you can search and aggregate in your log pipeline:

- **Inference completed:** `request_id`, `org_id`, `cache_hit`, `cache_tier`, `model_used`, `cost`
- **Inference request:** `request_id`, `org_id`
- **Auth failure:** audit log entry with `action=auth_failure`
- **API key created / policy update:** audit log with `action`, `org_id`, `user_id`

To get JSON logs (e.g. for Grafana Loki or CloudWatch), configure your process to use a JSON formatter. Options:

1. **Uvicorn:** run with a wrapper that sets `logging.config.dictConfig` to use a `pythonjsonlogger.jsonlogger.JsonFormatter` (or similar) for the root logger.
2. **Env:** if your deployment uses a logging env (e.g. `LOG_FORMAT=json`), ensure the app or `main.py` applies it when initialising logging.
3. **Config:** `config/models.yaml` or settings can expose `logging.format: json`; the app can call `logging.basicConfig` or dictConfig at startup based on that.

Each log line that uses `logger.info(..., extra={...})` will then appear as a single JSON object with level, message, and the extra keys (request_id, org_id, model_used, cost, cache_hit, etc.) for filtering and dashboards.
