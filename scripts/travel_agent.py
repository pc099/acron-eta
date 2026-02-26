#!/usr/bin/env python3
"""
Travel Agent — uses the ACRON API for travel queries (optimized inference + caching).

Usage:
  export ACRON_BASE_URL="https://your-api.railway.app"
  export ACRON_API_KEY="acron_sess_..."
  python scripts/travel_agent.py

  # One-shot query
  python scripts/travel_agent.py --query "Best 3-day itinerary for Rome"

  # Interactive (default)
  python scripts/travel_agent.py
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Optional, Tuple


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
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode()
            try:
                data = json.loads(raw) if raw else None
            except json.JSONDecodeError:
                data = None
            return resp.status, data, None
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()
        except Exception:
            err_body = ""
        return e.code, None, err_body or str(e)
    except urllib.error.URLError as e:
        return 0, None, str(e.reason) if getattr(e, "reason", None) else str(e)
    except Exception as e:
        return 0, None, str(e)


def ask_acron(
    base_url: str,
    api_key: str,
    prompt: str,
    routing_mode: str = "autopilot",
) -> Tuple[bool, Optional[str], Optional[dict]]:
    """Send a travel prompt to ACRON. Returns (success, response_text_or_error, full_response)."""
    payload = {
        "prompt": prompt,
        "routing_mode": routing_mode,
    }
    status, data, err = request(
        base_url,
        "/infer",
        method="POST",
        body=json.dumps(payload).encode(),
        api_key=api_key,
    )
    if status != 200 or data is None:
        return False, err or f"HTTP {status}", data
    return True, data.get("response", ""), data


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Travel agent using ACRON API (optimized inference + caching).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--base-url",
        default=env("ACRON_BASE_URL", "http://localhost:8000"),
        help="ACRON API base URL",
    )
    parser.add_argument(
        "--api-key",
        default=env("ACRON_API_KEY"),
        help="ACRON API key",
    )
    parser.add_argument(
        "--query",
        default=None,
        help="Single travel question (optional; without this, runs interactive mode)",
    )
    parser.add_argument(
        "--routing",
        default="autopilot",
        choices=["autopilot", "guided", "explicit"],
        help="Routing mode (default: autopilot)",
    )
    args = parser.parse_args()

    base = args.base_url.strip().rstrip("/")
    if not base:
        print("Error: base URL required (--base-url or ACRON_BASE_URL)", file=sys.stderr)
        return 2
    if not args.api_key:
        print("Error: API key required (--api-key or ACRON_API_KEY)", file=sys.stderr)
        return 2

    # Single query mode
    if args.query:
        prompt = (
            "You are a helpful travel agent. Answer concisely and practically. "
            + args.query.strip()
        )
        ok, text, resp = ask_acron(base, args.api_key, prompt, routing_mode=args.routing)
        if not ok:
            print(f"Error: {text}", file=sys.stderr)
            return 1
        print(text or "(no response)")
        if resp:
            cost = resp.get("cost", 0)
            model = resp.get("model_used", "?")
            cache = "cache hit" if resp.get("cache_hit") else "cache miss"
            print(f"\n[ACRON] model={model} | cost=${cost:.4f} | {cache}")
        return 0

    # Interactive mode
    print("Travel Agent (ACRON API)")
    print("Base URL:", base)
    print("Ask any travel question; empty line or 'quit' to exit.\n")

    while True:
        try:
            q = input("You: ").strip()
        except EOFError:
            break
        if not q or q.lower() in ("quit", "exit", "q"):
            break
        prompt = (
            "You are a helpful travel agent. Answer concisely and practically. " + q
        )
        ok, text, resp = ask_acron(base, args.api_key, prompt, routing_mode=args.routing)
        if not ok:
            print(f"Error: {text}\n")
            continue
        print(f"\nTravel Agent: {text or '(no response)'}")
        if resp:
            cost = resp.get("cost", 0)
            model = resp.get("model_used", "?")
            cache = "cache hit" if resp.get("cache_hit") else "cache miss"
            print(f"[ACRON] model={model} | cost=${cost:.4f} | {cache}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
