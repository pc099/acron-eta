---
name: asahi-inference-frontier
description: Solve difficult LLM inference-system problems in the Asahi codebase. Use when Codex needs to design or implement high-leverage improvements for routing, caching, workflow decomposition, batching, prompt or token optimization, evaluation strategy, latency or cost reduction, reliability hardening, or novel inference architecture ideas that must survive real engineering constraints rather than loose brainstorming.
---

# Asahi Inference Frontier

Treat the task as inference-systems engineering, not generic feature work. Push for ideas that improve the cost, latency, quality, reliability, or controllability frontier, then reduce them to code, tests, and measurable tradeoffs.

## Work Loop

1. Define the objective in one sentence.
   Include the current bottleneck, the metric that should move, and the hard constraint that must not regress.
2. Localize the problem before proposing changes.
   Read [references/repo-map.md](references/repo-map.md) to find the relevant files and to avoid mixing the prototype `src/` path with the production `backend/` path accidentally.
3. Generate three classes of hypotheses.
   Include one policy change, one state or cache change, and one instrumentation or evaluation change.
4. Rank options by expected leverage.
   Prefer ideas that can change the decision boundary of the system, not just micro-optimize a constant factor.
5. Pick one primary path and one fallback.
   State why the primary path is the best tradeoff for this repo now.
6. Implement the smallest convincing slice.
   Add or adjust tests, fixtures, or benchmark hooks so the change can be evaluated instead of argued abstractly.
7. Report what improved, what remains uncertain, and what to test next.

## Operating Rules

- Produce concrete proposals tied to files, modules, and data flow in this repo.
- Prefer mechanisms over adjectives. Replace "make it smarter" with a policy, thresholding rule, cache key strategy, queueing rule, evaluator, or feedback loop.
- Force every novel idea to name its failure mode, rollback path, and measurement plan.
- If the user asks for "unique ideas," still rank them and discard the ones that cannot be validated cheaply.
- When the existing architecture is the constraint, propose the minimal structural change that unlocks the next class of optimizations.
- Avoid hand-wavy model recommendations that ignore `config/models.yaml`, routing constraints, or tenant-scoped analytics.

## Decision Heuristics

Use [references/idea-patterns.md](references/idea-patterns.md) when the task needs a non-obvious design direction.

Prefer ideas that do at least one of these:

- Change routing from static thresholds to context-sensitive policies.
- Reuse work at a finer grain than full-response caching.
- Decompose requests so expensive reasoning is only applied where uncertainty is high.
- Add a closed-loop evaluator so routing and cache policy can improve from observed misses.
- Convert a serial path into asynchronous, batched, or speculative execution without breaking correctness.

Reject ideas that mainly add complexity without a crisp measurement story.

## Evaluation Standard

Use [references/eval-playbook.md](references/eval-playbook.md) whenever the task affects model choice, cache hit logic, prompt transformation, or execution order.

Do not claim improvement without at least one of:

- a targeted test that proves the new behavior,
- a replay or benchmark plan that compares old and new paths, or
- instrumentation that will expose whether the idea is working in production.

## Repo-Specific Focus Areas

### Routing

Inspect `src/routing/`, `src/models/registry.py`, `config/models.yaml`, and the optimizer entrypoint first.

Ask:

- Is the router making the right decision with the wrong inputs?
- Is the task detector too coarse?
- Should the system route uncertainty, not just task type?

### Caching

Inspect `src/cache/`, `src/embeddings/`, and workflow decomposition in `src/cache/workflow.py`.

Ask:

- Is the cache key too coarse or too strict?
- Can partial work be reused instead of final outputs only?
- Should semantic thresholding adapt to recompute cost or tenant behavior?

### Reliability and Throughput

Inspect `src/core/optimizer.py`, provider call paths, batching modules, tracker, and observability code.

Ask:

- Is the bottleneck synchronous provider I/O, queueing, or retry behavior?
- Can the system batch or speculate safely?
- Is fallback policy hiding real provider or routing failures?

### Productionization

Inspect `backend/` when the request is about the deployed SaaS backend, auth, DB-backed cache state, or API behavior. Keep prototype and production changes intentionally separated.

## Example Requests

- "Use `$asahi-inference-frontier` to redesign semantic cache thresholds so expensive prompts get more aggressive reuse without harming answer quality."
- "Use `$asahi-inference-frontier` to add an eval harness for routing decisions and show whether guided mode beats autopilot on cost per acceptable answer."
- "Use `$asahi-inference-frontier` to propose a novel batching or speculative execution strategy for the optimizer and implement the smallest viable version."
