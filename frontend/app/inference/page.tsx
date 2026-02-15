"use client";

import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { TextArea } from "@/components/Input";
import { infer, InferResponse } from "@/lib/api";

type RoutingMode = "autopilot" | "guided" | "explicit";
const QUALITY_OPTIONS = ["low", "medium", "high", "max"] as const;
const LATENCY_OPTIONS = ["slow", "normal", "fast", "instant"] as const;

export default function InferencePage() {
  const [prompt, setPrompt] = useState("");
  const [routingMode, setRoutingMode] = useState<RoutingMode>("autopilot");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<InferResponse | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [qualityThreshold, setQualityThreshold] = useState(3.5);
  const [latencyBudget, setLatencyBudget] = useState(1000);
  // Guided mode: user-overridable quality and latency preferences
  const [qualityPreference, setQualityPreference] = useState<typeof QUALITY_OPTIONS[number]>("medium");
  const [latencyPreference, setLatencyPreference] = useState<typeof LATENCY_OPTIONS[number]>("normal");
  // Explicit mode: user provides model and optional provider key
  const [modelOverride, setModelOverride] = useState("");
  const [providerApiKey, setProviderApiKey] = useState("");

  async function handleRun() {
    if (!prompt.trim()) {
      setError("Enter a prompt.");
      return;
    }
    if (routingMode === "explicit" && !modelOverride.trim()) {
      setError("In Explicit mode, enter a model name (e.g. gpt-4o, claude-3-5-sonnet).");
      return;
    }
    setError("");
    setResult(null);
    setLoading(true);
    try {
      const payload: Parameters<typeof infer>[0] = {
        prompt: prompt.trim(),
        routing_mode: routingMode,
        quality_threshold: qualityThreshold,
        latency_budget_ms: latencyBudget,
      };
      if (routingMode === "guided") {
        payload.quality_preference = qualityPreference;
        payload.latency_preference = latencyPreference;
      }
      if (routingMode === "explicit") {
        payload.model_override = modelOverride.trim();
      }
      const res = await infer(payload);
      setResult(res as InferResponse);
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
        <h3 className="text-lg font-bold text-white mb-4">Routing Mode</h3>
        <div className="flex flex-wrap gap-6">
          {(["autopilot", "guided", "explicit"] as const).map((mode) => (
            <label key={mode} className="flex items-center gap-2 cursor-pointer text-white">
              <input
                type="radio"
                name="routing"
                checked={routingMode === mode}
                onChange={() => setRoutingMode(mode)}
                className="text-acron-primary_accent focus:ring-acron-primary_accent"
              />
              <span className="font-medium capitalize">{mode}</span>
            </label>
          ))}
        </div>
        <div className="text-sm text-neutral-dark-gray mt-2 space-y-1">
          <p>
            {routingMode === "autopilot" && "Auto-detect task type and optimize cost. Best for most use cases."}
            {routingMode === "guided" && "You set quality and latency preferences; ACRON picks the best model within those constraints (e.g. high quality + low latency)."}
            {routingMode === "explicit" && "You specify the exact model name and optional provider API key. Use when you need a fixed model."}
          </p>
        </div>

        {routingMode === "guided" && (
          <div className="mt-4 pt-4 border-t border-neutral-border grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-white mb-1">Quality preference</label>
              <select
                value={qualityPreference}
                onChange={(e) => setQualityPreference(e.target.value as typeof qualityPreference)}
                className="w-full px-3 py-2 bg-neutral-dark border border-neutral-border rounded-card text-white focus:outline-none focus:border-acron-primary_accent"
              >
                {QUALITY_OPTIONS.map((q) => (
                  <option key={q} value={q} className="bg-neutral-dark">
                    {q.charAt(0).toUpperCase() + q.slice(1)}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-white mb-1">Latency preference</label>
              <select
                value={latencyPreference}
                onChange={(e) => setLatencyPreference(e.target.value as typeof latencyPreference)}
                className="w-full px-3 py-2 bg-neutral-dark border border-neutral-border rounded-card text-white focus:outline-none focus:border-acron-primary_accent"
              >
                {LATENCY_OPTIONS.map((l) => (
                  <option key={l} value={l} className="bg-neutral-dark">
                    {l.charAt(0).toUpperCase() + l.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}

        {routingMode === "explicit" && (
          <div className="mt-4 pt-4 border-t border-neutral-border grid gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-white mb-1">Model name (required)</label>
              <input
                type="text"
                placeholder="e.g. gpt-4o, claude-3-5-sonnet"
                value={modelOverride}
                onChange={(e) => setModelOverride(e.target.value)}
                className="w-full px-3 py-2 bg-neutral-dark border border-neutral-border rounded-card text-white placeholder-neutral-dark-gray focus:outline-none focus:border-acron-primary_accent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-white mb-1">Provider API key (optional)</label>
              <input
                type="password"
                placeholder="Your OpenAI/Anthropic/etc. key"
                value={providerApiKey}
                onChange={(e) => setProviderApiKey(e.target.value)}
                className="w-full px-3 py-2 bg-neutral-dark border border-neutral-border rounded-card text-white placeholder-neutral-dark-gray focus:outline-none focus:border-acron-primary_accent"
              />
              <p className="text-xs text-neutral-dark-gray mt-1">Use your own key for this model when set.</p>
            </div>
          </div>
        )}
      </Card>

      <Card className="mb-6">
        <h3 className="text-lg font-bold text-white mb-4">Prompt</h3>
        <TextArea
          label=""
          placeholder="Enter your prompt here..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          maxLength={5000}
          rows={5}
          className="bg-neutral-dark border-neutral-border text-white placeholder-neutral-dark-gray focus:border-acron-primary_accent"
        />
      </Card>

      <div className="mb-6">
        <button
          type="button"
          onClick={() => setAdvancedOpen(!advancedOpen)}
          className="flex items-center gap-2 text-white font-medium hover:text-neutral-dark-gray transition"
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
                  className="w-full px-3 py-2 bg-neutral-dark border border-neutral-border rounded-card text-white focus:outline-none focus:border-acron-primary_accent"
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
                  className="w-full px-3 py-2 bg-neutral-dark border border-neutral-border rounded-card text-white focus:outline-none focus:border-acron-primary_accent"
                />
              </div>
            </div>
          </Card>
        )}
      </div>

      <div className="flex gap-4 mb-8">
        <Button variant="secondary" onClick={handleClear} className="bg-neutral-light-gray text-white hover:bg-neutral-border">
          Clear
        </Button>
        <Button variant="primary" onClick={handleRun} disabled={loading}>
          {loading ? "Running…" : "Run Inference"}
        </Button>
      </div>

      {error && (
        <Card className="mb-6 border-semantic-error bg-red-900/20">
          <p className="text-semantic-error">{error}</p>
        </Card>
      )}

      <Card>
        <h3 className="text-lg font-bold text-white mb-4">Output</h3>
        {result ? (
          <>
            <div className="space-y-2 text-sm text-neutral-dark-gray mb-4">
              <p><strong className="text-white">Model:</strong> {result.model_used}</p>
              <p><strong className="text-white">Cost:</strong> ${typeof result.cost === "number" ? result.cost.toFixed(4) : result.cost}</p>
              <p>
                <strong className="text-white">Cache Hit:</strong>{" "}
                {result.cache_hit
                  ? `✓ Tier ${result.cache_tier ?? "?"} (${result.cache_tier === 2 ? "Semantic" : "Exact"} Match)`
                  : "✗"}
              </p>
              <p><strong className="text-white">Latency:</strong> {result.latency_ms}ms</p>
              {result.cost_savings_percent != null && (
                <p><strong className="text-white">Savings:</strong> {result.cost_savings_percent.toFixed(1)}%</p>
              )}
            </div>
            <div className="border-t border-neutral-border pt-4">
              <p className="text-sm font-medium text-white mb-2">Response text</p>
              <div className="p-4 bg-neutral-dark border border-neutral-border rounded-card whitespace-pre-wrap text-white min-h-[120px]">
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
          </>
        ) : (
          <div className="p-6 bg-neutral-dark border border-neutral-border rounded-card min-h-[140px] flex items-center justify-center">
            <p className="text-neutral-dark-gray">
              {loading ? "Running inference…" : "Run inference to see output here."}
            </p>
          </div>
        )}
      </Card>
    </DashboardLayout>
  );
}
