# Idea Patterns

Use this file when the current implementation works but the user needs a stronger design direction.

## 1. Change the decision policy

Replace fixed routing rules with a policy conditioned on uncertainty, expected recompute cost, tenant budget, or downstream fallback risk.

Examples:

- Route ambiguous prompts to a stronger model only when the task detector confidence is low.
- Route by expected answer utility per dollar, not only quality threshold.
- Add a cheap classifier or heuristic guard before calling the expensive router.

## 2. Change the reuse granularity

Reuse smaller units than full responses.

Examples:

- Cache extracted facts, summaries, or retrieved evidence separately from final wording.
- Cache workflow steps keyed by document segment or subproblem instead of the entire prompt.
- Promote recurrent tool outputs into reusable intermediate artifacts.

## 3. Change the execution shape

Change when and how work is executed.

Examples:

- Run retrieval, enrichment, and cheap classification in parallel.
- Start a cheap draft model speculatively, then cancel or upgrade based on confidence.
- Batch embedding generation or homogeneous low-priority requests.

## 4. Add feedback loops

Make the system learn from misses instead of preserving static heuristics forever.

Examples:

- Tune semantic thresholds from false-hit and false-miss observations.
- Track router overrides and use them as supervised signals.
- Detect prompts that frequently fall back and quarantine them into a stricter policy bucket.

## 5. Shift the objective

Sometimes the best solution is to optimize a better metric.

Examples:

- Optimize acceptable-answer rate under budget, not raw quality score.
- Optimize p95 latency for interactive workloads and total cost for offline workloads.
- Split tenant policies by workload class instead of one global default.

## Novelty Filter

Keep an idea only if it survives all three questions:

1. What concrete failure mode does it target?
2. What file or subsystem would change first?
3. How will the team know in one day or one week whether it worked?

If any answer is vague, the idea is still a thought experiment.
