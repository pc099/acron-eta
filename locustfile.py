"""
Minimal Locust load test for Asahi API (Phase 1.2).

Run: locust -f locustfile.py --host=http://localhost:8000
Then open http://localhost:8089 and start a swarm.
"""

import random
from locust import HttpUser, task, between


class AsahiInferUser(HttpUser):
    wait_time = between(0.5, 1.5)

    @task(3)
    def infer(self):
        self.client.post(
            "/infer",
            json={
                "prompt": f"Short prompt {random.randint(1, 1000)}",
                "routing_mode": "autopilot",
            },
            headers={"Content-Type": "application/json"},
            name="/infer",
        )

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
