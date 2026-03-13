# Eval Playbook

Use this file when changing routing, cache policy, prompt shaping, or execution order.

## Evaluation Ladder

1. Unit tests
   Prove deterministic rules, thresholds, and failure handling.
2. Replay tests
   Run a representative prompt set through old and new logic with mocks or captured metadata.
3. Metric comparison
   Compare cost, latency, cache hit rate, fallback rate, and quality proxy.
4. Shadow or canary plan
   Send a slice of traffic or offline traces through the new path before full rollout.

## Minimum Metrics

Track at least:

- request count,
- cache hit rate by tier,
- model selection distribution,
- fallback rate,
- input and output token deltas,
- p50 and p95 latency,
- cost per request,
- acceptable-answer proxy if available.

## Quality Proxies

If no gold labels exist, use proxies instead of pretending quality is unknowable.

- human spot checks on a small sampled set,
- consistency against stronger-model answers,
- structured rubric scoring for the target task,
- downstream task success if the response feeds another step.

## Regression Questions

Before shipping, answer:

1. Which tenants or task classes could regress first?
2. What kind of cache mistake is most dangerous: false hit or false miss?
3. What telemetry would reveal the regression quickly?
4. What configuration or code path rolls the change back?
