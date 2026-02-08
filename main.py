"""
CLI entry point for Asahi inference optimizer.

Usage:
    python main.py infer --prompt "..." --quality 3.5 --latency 300
    python main.py test --num_queries 50
    python main.py benchmark
    python main.py metrics
    python main.py api [--mock] [--port 5000]
"""

import argparse
import json
import os
import sys

from src.optimizer import InferenceOptimizer


def cmd_infer(args):
    """Run a single inference request."""
    optimizer = InferenceOptimizer(use_mock=args.mock)
    result = optimizer.infer(
        prompt=args.prompt,
        task_id="cli_infer",
        latency_budget_ms=args.latency,
        quality_threshold=args.quality,
        force_model=args.model,
    )
    print(json.dumps(result, indent=2))


def cmd_test(args):
    """Run test queries through the optimizer."""
    queries_path = os.path.join("data", "test_queries.json")
    if not os.path.exists(queries_path):
        print(f"Error: {queries_path} not found. Generate test data first.")
        sys.exit(1)

    with open(queries_path) as f:
        queries = json.load(f)

    n = min(args.num_queries, len(queries))
    print(f"Running {n} test queries (mock={args.mock})...\n")

    optimizer = InferenceOptimizer(use_mock=args.mock)

    for i, query in enumerate(queries[:n]):
        result = optimizer.infer(
            prompt=query["text"],
            task_id=query["id"],
            latency_budget_ms=args.latency,
            quality_threshold=args.quality,
        )
        print(
            f"  [{i+1}/{n}] {query['id']}: "
            f"model={result['model_used']}, "
            f"cost=${result['cost']:.4f}, "
            f"cache={'HIT' if result['cache_hit'] else 'MISS'}"
        )

    metrics = optimizer.get_metrics()
    print(f"\n--- Results ---")
    print(json.dumps(metrics, indent=2))

    # Save results
    optimizer.tracker.save_summary("optimized_results.json")
    print(f"\nSummary saved to data/optimized_results.json")


def cmd_benchmark(args):
    """Run baseline (all GPT-4) vs optimized comparison."""
    queries_path = os.path.join("data", "test_queries.json")
    if not os.path.exists(queries_path):
        print(f"Error: {queries_path} not found.")
        sys.exit(1)

    with open(queries_path) as f:
        queries = json.load(f)

    n = min(args.num_queries, len(queries))
    print(f"Benchmarking {n} queries (mock={args.mock})...\n")

    # --- Baseline: force all to GPT-4 ---
    print("=== BASELINE (All GPT-4-Turbo) ===")
    baseline = InferenceOptimizer(use_mock=args.mock)
    for i, query in enumerate(queries[:n]):
        baseline.infer(
            prompt=query["text"],
            task_id=f"baseline_{query['id']}",
            latency_budget_ms=9999,
            quality_threshold=0,
            force_model="gpt-4-turbo",
        )
        if (i + 1) % 10 == 0:
            print(f"  Baseline: {i+1}/{n}")
    baseline_metrics = baseline.get_metrics()
    baseline.tracker.save_summary("baseline_results.json")

    # --- Optimized: smart routing ---
    print("\n=== OPTIMIZED (Smart Routing) ===")
    optimized = InferenceOptimizer(use_mock=args.mock)
    for i, query in enumerate(queries[:n]):
        optimized.infer(
            prompt=query["text"],
            task_id=f"optimized_{query['id']}",
            latency_budget_ms=300,
            quality_threshold=3.5,
        )
        if (i + 1) % 10 == 0:
            print(f"  Optimized: {i+1}/{n}")
    optimized_metrics = optimized.get_metrics()
    optimized.tracker.save_summary("optimized_results.json")

    # --- Comparison ---
    b_cost = baseline_metrics["total_cost"]
    o_cost = optimized_metrics["total_cost"]
    savings_pct = ((b_cost - o_cost) / b_cost * 100) if b_cost > 0 else 0

    print(f"""
{'='*50}
           BENCHMARK RESULTS
{'='*50}

BASELINE (All GPT-4-Turbo):
  Total Cost:     ${b_cost:.4f}
  Avg Latency:    {baseline_metrics['avg_latency_ms']:.0f}ms
  Requests:       {baseline_metrics['requests']}

OPTIMIZED (Smart Routing):
  Total Cost:     ${o_cost:.4f}
  Avg Latency:    {optimized_metrics['avg_latency_ms']:.0f}ms
  Cache Hit Rate: {optimized_metrics['cache_hit_rate']:.1%}
  Models Used:    {optimized_metrics.get('requests_by_model', {})}

SAVINGS:
  Cost Reduction: {savings_pct:.1f}%
  Absolute:       ${b_cost - o_cost:.4f}
  Per Request:    ${b_cost/max(1,baseline_metrics['requests']):.6f} -> ${o_cost/max(1,optimized_metrics['requests']):.6f}

{'='*50}
""")


def cmd_metrics(args):
    """Show metrics from saved results."""
    for name in ["baseline_results.json", "optimized_results.json"]:
        path = os.path.join("data", name)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            print(f"\n--- {name} ---")
            print(json.dumps(data, indent=2))
        else:
            print(f"{name}: not found (run benchmark first)")


def cmd_api(args):
    """Start the Flask REST API server."""
    from src.api import create_app

    app = create_app(use_mock=args.mock)
    print(f"Starting Asahi API on port {args.port} (mock={args.mock})")
    app.run(host="0.0.0.0", port=args.port, debug=True)


def main():
    parser = argparse.ArgumentParser(
        description="Asahi - Inference Cost Optimizer"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # infer
    p_infer = subparsers.add_parser("infer", help="Run single inference")
    p_infer.add_argument("--prompt", required=True, help="Input prompt")
    p_infer.add_argument("--quality", type=float, default=3.5)
    p_infer.add_argument("--latency", type=int, default=300)
    p_infer.add_argument("--model", default=None, help="Force specific model")
    p_infer.add_argument("--mock", action="store_true", help="Use mock inference")

    # test
    p_test = subparsers.add_parser("test", help="Run test queries")
    p_test.add_argument("--num_queries", type=int, default=50)
    p_test.add_argument("--quality", type=float, default=3.5)
    p_test.add_argument("--latency", type=int, default=300)
    p_test.add_argument("--mock", action="store_true", help="Use mock inference")

    # benchmark
    p_bench = subparsers.add_parser("benchmark", help="Baseline vs optimized")
    p_bench.add_argument("--num_queries", type=int, default=50)
    p_bench.add_argument("--mock", action="store_true", help="Use mock inference")

    # metrics
    subparsers.add_parser("metrics", help="Show saved metrics")

    # api
    p_api = subparsers.add_parser("api", help="Start REST API server")
    p_api.add_argument("--port", type=int, default=5000)
    p_api.add_argument("--mock", action="store_true", help="Use mock inference")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "infer": cmd_infer,
        "test": cmd_test,
        "benchmark": cmd_benchmark,
        "metrics": cmd_metrics,
        "api": cmd_api,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
