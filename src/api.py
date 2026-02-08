"""
Flask REST API for Asahi inference optimizer.

Endpoints:
    POST /infer   - Run inference with smart routing
    GET  /metrics - View cost/latency/quality analytics
    GET  /health  - Health check
"""

import time

from flask import Flask, request, jsonify

from src.optimizer import InferenceOptimizer


def create_app(use_mock: bool = False) -> Flask:
    app = Flask(__name__)
    optimizer = InferenceOptimizer(use_mock=use_mock)
    start_time = time.time()

    @app.route("/infer", methods=["POST"])
    def infer():
        data = request.get_json(silent=True) or {}

        prompt = data.get("prompt", "")
        if not prompt:
            return jsonify({"error": "prompt is required"}), 400

        result = optimizer.infer(
            prompt=prompt,
            task_id=data.get("task_id", ""),
            latency_budget_ms=data.get("latency_budget_ms", 300),
            quality_threshold=data.get("quality_threshold", 3.5),
            cost_budget=data.get("cost_budget"),
            force_model=data.get("force_model"),
        )

        return jsonify(result)

    @app.route("/metrics", methods=["GET"])
    def metrics():
        return jsonify(optimizer.get_metrics())

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "healthy",
            "uptime_seconds": round(time.time() - start_time, 1),
        })

    return app
