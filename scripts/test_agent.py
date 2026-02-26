#!/usr/bin/env python3
"""
ACRON Testing Agent — connectivity and usage checks.

Usage:
  # Env vars (recommended; do not commit API keys)
  export ACRON_BASE_URL="https://your-api.railway.app"
  export ACRON_API_KEY="acron_sess_..."
  python scripts/test_agent.py

  # CLI
  python scripts/test_agent.py --base-url https://your-api.railway.app --api-key "acron_sess_..."

  # From repo root
  python -m scripts.test_agent
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Callable, Optional, Tuple


def env(name: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(name, default)


def request(
    base_url: str,
    path: str,
    method: str = "GET",
    body: Optional[bytes] = None,
    api_key: Optional[str] = None,
) -> Tuple[int, Optional[Any], Optional[str]]:
    """Return (status_code, parsed_json_or_none, error_message)."""
    url = f"{base_url.rstrip('/')}{path}"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            try:
                data = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                data = None
            return resp.status, data, None
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
        except Exception:
            body = ""
        return e.code, None, body or str(e)
    except urllib.error.URLError as e:
        return 0, None, str(e.reason) if getattr(e, "reason", None) else str(e)
    except Exception as e:
        return 0, None, str(e)


def check(
    name: str,
    ok: bool,
    detail: str = "",
    data: Optional[Any] = None,
) -> bool:
    status = "PASS" if ok else "FAIL"
    line = f"  [{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    if data is not None and not ok and isinstance(data, dict):
        err = data.get("error") or data.get("detail") or data.get("message")
        if err:
            print(f"       {err}")
    return ok


def run_checks(base_url: str, api_key: Optional[str]) -> int:
    failures = 0

    # 1. Connectivity — health (no auth)
    print("\n--- Connectivity ---")
    status, data, err = request(base_url, "/health", api_key=None)
    ok = status == 200 and data is not None
    if ok and isinstance(data, dict):
        cache_backend = data.get("cache_backend", "?")
        detail = f"status={data.get('status')}, cache_backend={cache_backend}"
    else:
        detail = err or f"status={status}"
    if not check("GET /health", ok, detail, data if not ok else None):
        failures += 1

    if not api_key:
        print("\n  (Skipping auth-required checks; set ACRON_API_KEY to run full usage tests.)")
        return failures

    # 2. Metrics (auth required)
    print("\n--- Usage (authenticated) ---")
    status, data, err = request(base_url, "/metrics", api_key=api_key)
    ok = status == 200 and data is not None
    if ok and isinstance(data, dict):
        reqs = data.get("requests", 0)
        cost = data.get("total_cost", 0)
        detail = f"requests={reqs}, total_cost={cost}"
    else:
        detail = err or f"status={status}"
    if not check("GET /metrics", ok, detail, data if not ok else None):
        failures += 1

    # 3. Inference
    status, data, err = request(
        base_url,
        "/infer",
        method="POST",
        body=json.dumps({"prompt": "Say hello in one word.", "routing_mode": "autopilot"}).encode(),
        api_key=api_key,
    )
    ok = status == 200 and data is not None
    if ok and isinstance(data, dict):
        model = data.get("model_used", "?")
        cost = data.get("cost", 0)
        cache = "hit" if data.get("cache_hit") else "miss"
        detail = f"model={model}, cost={cost}, cache={cache}"
    else:
        detail = err or f"status={status}"
    if not check("POST /infer", ok, detail, data if not ok else None):
        failures += 1

    # 4. Cost summary
    status, data, err = request(
        base_url,
        "/analytics/cost-summary?period=24h",
        api_key=api_key,
    )
    ok = status == 200 and data is not None
    if ok and isinstance(data, dict):
        inner = data.get("data") or data
        total = inner.get("total_cost", 0)
        reqs = inner.get("total_requests", 0)
        detail = f"total_cost={total}, total_requests={reqs}"
    else:
        detail = err or f"status={status}"
    if not check("GET /analytics/cost-summary", ok, detail, data if not ok else None):
        failures += 1

    # 5. Recent inferences
    status, data, err = request(
        base_url,
        "/analytics/recent-inferences?limit=5",
        api_key=api_key,
    )
    ok = status == 200 and data is not None
    if ok and isinstance(data, dict):
        inner = data.get("data") or data
        inferences = inner.get("inferences") or []
        count = inner.get("count", len(inferences))
        detail = f"count={count}"
    else:
        detail = err or f"status={status}"
    if not check("GET /analytics/recent-inferences", ok, detail, data if not ok else None):
        failures += 1

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ACRON testing agent: connectivity and usage checks.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--base-url",
        default=env("ACRON_BASE_URL", "http://localhost:8000"),
        help="API base URL (default: ACRON_BASE_URL or http://localhost:8000)",
    )
    parser.add_argument(
        "--api-key",
        default=env("ACRON_API_KEY"),
        help="API key for authenticated checks (default: ACRON_API_KEY)",
    )
    args = parser.parse_args()

    base = args.base_url.strip().rstrip("/")
    if not base:
        print("Error: base URL is required (--base-url or ACRON_BASE_URL)", file=sys.stderr)
        return 2

    print(f"Base URL: {base}")
    print(f"API key:  {'(set)' if args.api_key else '(not set — auth checks skipped)'}")

    failures = run_checks(base, args.api_key)

    print()
    if failures == 0:
        print("All checks passed.")
        return 0
    print(f"{failures} check(s) failed.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
