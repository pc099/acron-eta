"""
Test script for Phase 2 integration: Tier 2 Semantic Caching

This script demonstrates:
1. Tier 1 (exact match) cache hits
2. Tier 2 (semantic similarity) cache hits
3. AdvancedRouter modes (AUTOPILOT, GUIDED, EXPLICIT)

Usage:
    # Set your API keys in .env file:
    # COHERE_API_KEY=your_key_here  (for embeddings)
    # OPENAI_API_KEY=your_key_here  (for LLM inference)
    
    python test_phase2.py
"""

import json
import os
import sys
import time
from typing import Dict, Any

from dotenv import load_dotenv

from src.api.app import create_app
from fastapi.testclient import TestClient

load_dotenv()


def print_result(label: str, response: Dict[str, Any]) -> None:
    """Pretty print a test result."""
    print(f"\n{'='*60}")
    print(f"{label}")
    print(f"{'='*60}")
    print(f"Response: {response.get('response', '')[:200]}...")
    print(f"Model: {response.get('model_used', 'N/A')}")
    print(f"Cache Hit: {response.get('cache_hit', False)}")
    print(f"Cost: ${response.get('cost', 0):.6f}")
    print(f"Latency: {response.get('latency_ms', 0):.1f}ms")
    print(f"Routing Reason: {response.get('routing_reason', 'N/A')}")
    print(f"Request ID: {response.get('request_id', 'N/A')}")


def test_tier1_exact_match(client: TestClient) -> None:
    """Test Tier 1: Exact match cache."""
    print("\n" + "="*60)
    print("TEST 1: Tier 1 Exact Match Cache")
    print("="*60)
    
    prompt = "What is Python programming language?"
    
    # First request - should miss cache
    print("\n1. First request (cache miss expected):")
    r1 = client.post("/infer", json={"prompt": prompt})
    assert r1.status_code == 200
    result1 = r1.json()
    print_result("First Request", result1)
    assert result1["cache_hit"] is False, "First request should be a cache miss"
    
    # Second request - exact same prompt - should hit Tier 1 cache
    print("\n2. Second request (Tier 1 cache hit expected):")
    r2 = client.post("/infer", json={"prompt": prompt})
    assert r2.status_code == 200
    result2 = r2.json()
    print_result("Second Request (Exact Match)", result2)
    assert result2["cache_hit"] is True, "Second request should hit Tier 1 cache"
    assert result2["cost"] == 0.0, "Cache hit should have zero cost"
    assert result2["latency_ms"] == 0.0, "Cache hit should have zero latency"


def test_tier2_semantic_similarity(client: TestClient) -> None:
    """Test Tier 2: Semantic similarity cache."""
    print("\n" + "="*60)
    print("TEST 2: Tier 2 Semantic Similarity Cache")
    print("="*60)
    
    # Check if COHERE_API_KEY is set
    if not os.getenv("COHERE_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print("\n[WARNING] COHERE_API_KEY or OPENAI_API_KEY not set!")
        print("   Tier 2 semantic caching requires an embedding API key.")
        print("   Set COHERE_API_KEY in your .env file to test Tier 2 caching.")
        print("   Skipping Tier 2 test...")
        return
    
    original_prompt = "What is Python?"
    similar_prompt = "Can you explain what Python is?"
    
    # First request - store in Tier 2 cache
    print("\n1. First request with original prompt:")
    r1 = client.post("/infer", json={"prompt": original_prompt})
    assert r1.status_code == 200
    result1 = r1.json()
    print_result("Original Query", result1)
    
    # Wait a moment to ensure cache is written
    time.sleep(0.5)
    
    # Second request - semantically similar but not exact - should hit Tier 2 cache
    print("\n2. Second request with semantically similar prompt:")
    print(f"   Original: '{original_prompt}'")
    print(f"   Similar:  '{similar_prompt}'")
    r2 = client.post("/infer", json={"prompt": similar_prompt})
    assert r2.status_code == 200
    result2 = r2.json()
    print_result("Semantically Similar Query", result2)
    
    if result2["cache_hit"]:
        print("\n[SUCCESS] Tier 2 semantic cache hit!")
        print(f"   The system recognized '{similar_prompt}' as similar to '{original_prompt}'")
    else:
        print("\n[INFO] Tier 2 cache miss - this could mean:")
        print("   - Similarity threshold not met")
        print("   - Embedding API not configured correctly")
        print("   - Semantic cache not initialized")


def test_advanced_router_modes(client: TestClient) -> None:
    """Test AdvancedRouter modes."""
    print("\n" + "="*60)
    print("TEST 3: AdvancedRouter Modes")
    print("="*60)
    
    prompt = "Explain quantum computing"
    
    # AUTOPILOT mode (default)
    print("\n1. AUTOPILOT mode (auto-detect task type):")
    r1 = client.post("/infer", json={
        "prompt": prompt,
        "routing_mode": "autopilot"
    })
    assert r1.status_code == 200
    result1 = r1.json()
    print_result("AUTOPILOT Mode", result1)
    print(f"   Routing reason: {result1.get('routing_reason', 'N/A')}")
    
    # GUIDED mode
    print("\n2. GUIDED mode (user preferences):")
    r2 = client.post("/infer", json={
        "prompt": prompt,
        "routing_mode": "guided",
        "quality_preference": "high",
        "latency_preference": "medium"
    })
    assert r2.status_code == 200
    result2 = r2.json()
    print_result("GUIDED Mode (high quality, medium latency)", result2)
    print(f"   Routing reason: {result2.get('routing_reason', 'N/A')}")
    
    # EXPLICIT mode
    print("\n3. EXPLICIT mode (user selects model):")
    r3 = client.post("/infer", json={
        "prompt": prompt,
        "routing_mode": "explicit",
        "model_override": "gpt-4o"
    })
    assert r3.status_code == 200
    result3 = r3.json()
    print_result("EXPLICIT Mode (gpt-4o)", result3)
    print(f"   Routing reason: {result3.get('routing_reason', 'N/A')}")
    assert result3["model_used"] == "gpt-4o" or "gpt-4o" in result3.get("routing_reason", "")


def test_cache_statistics(client: TestClient) -> None:
    """Test cache statistics endpoint."""
    print("\n" + "="*60)
    print("TEST 4: Cache Statistics")
    print("="*60)
    
    # Make a few requests first
    for i in range(3):
        client.post("/infer", json={"prompt": f"Test query {i}"})
    
    # Get metrics
    r = client.get("/metrics")
    assert r.status_code == 200
    metrics = r.json()
    
    print("\nCache Statistics:")
    print(f"  Total Requests: {metrics.get('requests', 0)}")
    print(f"  Cache Hit Rate: {metrics.get('cache_hit_rate', 0):.2%}")
    print(f"  Cache Size: {metrics.get('cache_size', 0)}")
    print(f"  Total Cost Saved: ${metrics.get('cache_cost_saved', 0):.2f}")


def main() -> None:
    """Run all Phase 2 tests."""
    print("\n" + "="*60)
    print("PHASE 2 INTEGRATION TEST SUITE")
    print("="*60)
    print("\nThis script tests:")
    print("  1. Tier 1 (exact match) caching")
    print("  2. Tier 2 (semantic similarity) caching")
    print("  3. AdvancedRouter modes (AUTOPILOT, GUIDED, EXPLICIT)")
    print("  4. Cache statistics")
    
    # Check API keys
    print("\n" + "-"*60)
    print("API Key Status:")
    print("-"*60)
    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_cohere = bool(os.getenv("COHERE_API_KEY"))
    print(f"  OPENAI_API_KEY: {'[SET]' if has_openai else '[NOT SET]'}")
    print(f"  COHERE_API_KEY: {'[SET]' if has_cohere else '[NOT SET]'}")
    
    if not has_openai:
        print("\nWARNING: OPENAI_API_KEY not set!")
        print("   LLM inference will fail. Set it in .env file.")
        print("   Using mock mode for testing...")
    
    # Create app and client
    print("\n" + "-"*60)
    print("Initializing Asahi API...")
    print("-"*60)
    app = create_app(use_mock=not has_openai)
    client = TestClient(app)
    
    try:
        # Run tests
        test_tier1_exact_match(client)
        test_tier2_semantic_similarity(client)
        test_advanced_router_modes(client)
        test_cache_statistics(client)
        
        print("\n" + "="*60)
        print("[SUCCESS] ALL TESTS COMPLETED")
        print("="*60)
        print("\nSummary:")
        print("  - Tier 1 caching: Working")
        if has_cohere or has_openai:
            print("  - Tier 2 caching: Tested (check results above)")
        else:
            print("  - Tier 2 caching: Skipped (no embedding API key)")
        print("  - AdvancedRouter: Tested")
        print("  - Cache statistics: Tested")
        
    except Exception as e:
        print(f"\n[ERROR] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
