"use client";

import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { TextArea } from "@/components/Input";
import { infer, InferResponse } from "@/lib/api";

type RoutingMode = "autopilot" | "guided" | "explicit";

export default function InferencePage() {
  const [prompt, setPrompt] = useState("");
  const [routingMode, setRoutingMode] = useState<RoutingMode>("autopilot");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<InferResponse | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [qualityThreshold, setQualityThreshold] = useState(3.5);
  const [latencyBudget, setLatencyBudget] = useState(1000);

  async function handleRun() {
    if (!prompt.trim()) {
      setError("Enter a prompt.");
      return;
    }
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const res = await infer({
        prompt: prompt.trim(),
        routing_mode: routingMode,
        quality_threshold: qualityThreshold,
        latency_budget_ms: latencyBudget,
      });
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Inference failed.");
    } finally {
      setLoading(false);
    }
  }

  function handleClear() {
    setPrompt("");
    setResult(null);
    setError("");
  }

  return (
    <DashboardLayout
      title="Inference Testing"
      subtitle="Run and monitor inference requests"
    >
      <Card className="mb-6">
        <h3 className="text-lg font-bold text-neutral-dark mb-4">Routing Mode</h3>
        <div className="flex flex-wrap gap-6">
          {(["autopilot", "guided", "explicit"] as const).map((mode) => (
            <label key={mode} className="flex items-center gap-2 cursor-pointer">
              <input
                type="radio"
                name="routing"
                checked={routingMode === mode}
                onChange={() => setRoutingMode(mode)}
                className="text-asahi-orange focus:ring-asahi-orange"
              />
              <span className="font-medium capitalize">{mode}</span>
            </label>
          ))}
        </div>
        <p className="text-sm text-neutral-dark-gray mt-2">
          {routingMode === "autopilot" &&
            "Auto-detect task type and optimize cost."}
          {routingMode === "guided" && "Set quality/latency preferences."}
          {routingMode === "explicit" && "Use a specific model override."}
        </p>
      </Card>

      <Card className="mb-6">
        <h3 className="text-lg font-bold text-neutral-dark mb-4">Prompt</h3>
        <TextArea
          label=""
          placeholder="Enter your prompt here..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          maxLength={5000}
          rows={5}
        />
      </Card>

      <div className="mb-6">
        <button
          type="button"
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className="flex items-center gap-2 text-neutral-dark font-medium"
        >
          {advancedOpen ? "▼" : "▶"} Advanced Options
        </button>
        {advancedOpen && (
          <Card className="mt-2">
            <div className="grid md:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-neutral-dark-gray mb-1">
                  Quality Threshold (0–5)
                </label>
                <input
                  type="number"
                  min={0}
                  max={5}
                  step={0.1}
                  value={qualityThreshold}
                  onChange={(e) => setQualityThreshold(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-neutral-border rounded-card"
                />
              </div>
              <div>
                <label className="block text-sm text-neutral-dark-gray mb-1">
                  Latency Budget (ms)
                </label>
                <input
                  type="number"
                  min={100}
                  value={latencyBudget}
                  onChange={(e) => setLatencyBudget(Number(e.target.value))}
                  className="w-full px-3 py-2 border border-neutral-border rounded-card"
                />
              </div>
            </div>
          </Card>
        )}
      </div>

      <div className="flex gap-4 mb-8">
        <Button variant="secondary" onClick={handleClear}>
          Clear
        </Button>
        <Button variant="primary" onClick={handleRun} disabled={loading}>
          {loading ? "Running…" : "Run Inference"}
        </Button>
      </div>

      {error && (
        <Card className="mb-6 border-semantic-error bg-red-50">
          <p className="text-semantic-error">{error}</p>
        </Card>
      )}

      {result && (
        <Card>
          <h3 className="text-lg font-bold text-neutral-dark mb-4">Response</h3>
          <div className="space-y-2 text-sm text-neutral-dark-gray mb-4">
            <p><strong>Model:</strong> {result.model_used}</p>
            <p><strong>Cost:</strong> ${result.cost.toFixed(4)}</p>
            <p>
              <strong>Cache Hit:</strong>{" "}
              {result.cache_hit
                ? `✓ Tier ${result.cache_tier ?? "?"} (${result.cache_tier === 2 ? "Semantic" : "Exact"} Match)`
                : "✗"}
            </p>
            <p><strong>Latency:</strong> {result.latency_ms}ms</p>
            {result.cost_savings_percent != null && (
              <p><strong>Savings:</strong> {result.cost_savings_percent.toFixed(1)}%</p>
            )}
          </div>
          <div className="border-t border-neutral-border pt-4">
            <p className="text-sm font-medium text-neutral-dark mb-2">Response text</p>
            <div className="p-4 bg-neutral-light-gray rounded-card whitespace-pre-wrap text-neutral-dark">
              {result.response || "(empty)"}
            </div>
          </div>
          <div className="mt-4 flex gap-4">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigator.clipboard.writeText(result.response)}
            >
              Copy Response
            </Button>
            <Button variant="ghost" size="sm" onClick={handleClear}>
              New Request
            </Button>
          </div>
        </Card>
      )}
    </DashboardLayout>
  );
}
