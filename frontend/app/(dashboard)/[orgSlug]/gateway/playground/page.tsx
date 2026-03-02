"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { chatCompletions } from "@/lib/api";
import type { ChatCompletionResponse } from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";
import {
  Play,
  Loader2,
  Cpu,
  Database,
  DollarSign,
  Clock,
  TrendingDown,
  Sparkles,
  ChevronDown,
} from "lucide-react";

const ROUTING_MODES = ["AUTOPILOT", "GUIDED", "EXPLICIT"] as const;

const MODE_DESCRIPTIONS: Record<string, string> = {
  AUTOPILOT: "Auto-detects task type and selects the cheapest model that meets quality requirements",
  GUIDED: "You set quality and latency preferences, ASAHI picks the best model",
  EXPLICIT: "You choose the exact model — ASAHI shows what you could save with alternatives",
};

// Maps frontend quality labels to backend-expected values
const QUALITY_OPTIONS = [
  { label: "Economy", value: "low" },
  { label: "Balanced", value: "medium" },
  { label: "High", value: "high" },
  { label: "Max", value: "max" },
] as const;

const LATENCY_OPTIONS = [
  { label: "Relaxed", value: "slow" },
  { label: "Normal", value: "normal" },
  { label: "Fast", value: "fast" },
  { label: "Instant", value: "instant" },
] as const;

const AVAILABLE_MODELS = [
  { id: "gpt-4o", label: "GPT-4o", provider: "OpenAI" },
  { id: "claude-opus-4", label: "Claude Opus 4", provider: "Anthropic" },
  { id: "claude-3-5-sonnet", label: "Claude 3.5 Sonnet", provider: "Anthropic" },
];

export default function PlaygroundPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : undefined;
  const [routingMode, setRoutingMode] = useState<string>("AUTOPILOT");
  const [qualityIndex, setQualityIndex] = useState(1);
  const [latencyIndex, setLatencyIndex] = useState(1);
  const [selectedModel, setSelectedModel] = useState(AVAILABLE_MODELS[0].id);
  const [message, setMessage] = useState("");
  const [result, setResult] = useState<ChatCompletionResponse | null>(null);

  const mutation = useMutation({
    mutationFn: (userMessage: string) =>
      chatCompletions(
        {
          messages: [{ role: "user", content: userMessage }],
          routing_mode: routingMode,
          quality_preference: QUALITY_OPTIONS[qualityIndex].value,
          latency_preference: LATENCY_OPTIONS[latencyIndex].value,
          ...(routingMode === "EXPLICIT" ? { model: selectedModel } : {}),
        },
        undefined,
        orgSlug
      ),
    onSuccess: (data) => setResult(data),
  });

  const handleRun = () => {
    if (!message.trim()) return;
    mutation.mutate(message.trim());
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Playground</h1>
        <p className="text-sm text-muted-foreground">
          Test inference requests and see ASAHI optimization in action
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Left panel - Input */}
        <div className="space-y-4">
          {/* Routing mode */}
          <div className="rounded-lg border border-border bg-card p-4">
            <label className="mb-3 block text-sm font-medium text-foreground">
              Routing Mode
            </label>
            <div className="flex gap-2">
              {ROUTING_MODES.map((mode) => (
                <button
                  key={mode}
                  onClick={() => setRoutingMode(mode)}
                  className={cn(
                    "flex-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    routingMode === mode
                      ? "bg-asahi text-white"
                      : "border border-border bg-background text-muted-foreground hover:text-foreground"
                  )}
                >
                  {mode}
                </button>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {MODE_DESCRIPTIONS[routingMode]}
            </p>
          </div>

          {/* EXPLICIT mode — model selector */}
          {routingMode === "EXPLICIT" && (
            <div className="rounded-lg border border-border bg-card p-4">
              <label className="mb-3 block text-sm font-medium text-foreground">
                Model
              </label>
              <div className="relative">
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="w-full appearance-none rounded-md border border-border bg-background px-4 py-2.5 pr-10 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-asahi"
                >
                  {AVAILABLE_MODELS.map((m) => (
                    <option key={m.id} value={m.id}>
                      {m.label} ({m.provider})
                    </option>
                  ))}
                </select>
                <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              </div>
            </div>
          )}

          {/* GUIDED mode — quality + latency preferences */}
          {routingMode === "GUIDED" && (
            <>
              <div className="rounded-lg border border-border bg-card p-4">
                <label className="mb-3 block text-sm font-medium text-foreground">
                  Quality Preference
                </label>
                <input
                  type="range"
                  min={0}
                  max={3}
                  step={1}
                  value={qualityIndex}
                  onChange={(e) => setQualityIndex(Number(e.target.value))}
                  className="w-full accent-asahi"
                />
                <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                  {QUALITY_OPTIONS.map((q, i) => (
                    <span
                      key={q.value}
                      className={cn(qualityIndex === i && "text-asahi font-medium")}
                    >
                      {q.label}
                    </span>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <label className="mb-3 block text-sm font-medium text-foreground">
                  Latency Preference
                </label>
                <input
                  type="range"
                  min={0}
                  max={3}
                  step={1}
                  value={latencyIndex}
                  onChange={(e) => setLatencyIndex(Number(e.target.value))}
                  className="w-full accent-asahi"
                />
                <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                  {LATENCY_OPTIONS.map((l, i) => (
                    <span
                      key={l.value}
                      className={cn(latencyIndex === i && "text-asahi font-medium")}
                    >
                      {l.label}
                    </span>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* AUTOPILOT mode — simplified quality slider */}
          {routingMode === "AUTOPILOT" && (
            <div className="rounded-lg border border-border bg-card p-4">
              <label className="mb-3 block text-sm font-medium text-foreground">
                Quality Preference
              </label>
              <input
                type="range"
                min={0}
                max={3}
                step={1}
                value={qualityIndex}
                onChange={(e) => setQualityIndex(Number(e.target.value))}
                className="w-full accent-asahi"
              />
              <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                {QUALITY_OPTIONS.map((q, i) => (
                  <span
                    key={q.value}
                    className={cn(qualityIndex === i && "text-asahi font-medium")}
                  >
                    {q.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Message input */}
          <div className="rounded-lg border border-border bg-card p-4">
            <label className="mb-3 block text-sm font-medium text-foreground">
              Message
            </label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Enter your prompt here..."
              rows={6}
              className="w-full resize-none rounded-md border border-border bg-background px-4 py-3 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-asahi"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRun();
              }}
            />
          </div>

          {/* Run button */}
          <button
            onClick={handleRun}
            disabled={!message.trim() || mutation.isPending}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-asahi px-4 py-3 text-sm font-medium text-white hover:bg-asahi-dark disabled:opacity-50 transition-colors"
          >
            {mutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="h-4 w-4" />
                Run Inference
              </>
            )}
          </button>
        </div>

        {/* Right panel - Response */}
        <div className="space-y-4">
          {/* Response display */}
          <div className="rounded-lg border border-border bg-card p-4">
            <h3 className="mb-3 text-sm font-medium text-foreground">
              Response
            </h3>
            {mutation.isPending ? (
              <div className="animate-pulse space-y-3">
                <div className="h-4 w-3/4 rounded bg-muted" />
                <div className="h-4 w-full rounded bg-muted" />
                <div className="h-4 w-5/6 rounded bg-muted" />
                <div className="h-4 w-2/3 rounded bg-muted" />
              </div>
            ) : mutation.isError ? (
              <div className="rounded-md border border-red-500/30 bg-red-500/10 p-4">
                <p className="text-sm font-medium text-red-400">Request failed</p>
                <p className="mt-1 text-sm text-red-300/90 break-words">
                  {mutation.error instanceof Error
                    ? mutation.error.message
                    : "An error occurred"}
                </p>
              </div>
            ) : result ? (
              <div className="whitespace-pre-wrap text-sm text-foreground leading-relaxed">
                {result.choices[0]?.message.content || "No response content"}
              </div>
            ) : (
              <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
                Run a request to see the response here.
              </div>
            )}
          </div>

          {/* Metadata cards */}
          {result && (
            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Cpu className="h-3.5 w-3.5" />
                  Model Used
                </div>
                <p className="mt-1 font-mono text-sm font-medium text-foreground">
                  {result.asahi.model_used}
                </p>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Database className="h-3.5 w-3.5" />
                  Cache Tier
                </div>
                <p className="mt-1 text-sm font-medium text-foreground">
                  {result.asahi.cache_hit
                    ? result.asahi.cache_tier || "hit"
                    : "miss"}
                </p>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <DollarSign className="h-3.5 w-3.5" />
                  Cost
                </div>
                <p className="mt-1 text-sm font-medium text-foreground">
                  {formatCurrency(result.asahi.cost_with_asahi)}
                </p>
                <p className="text-xs text-muted-foreground">
                  vs {formatCurrency(result.asahi.cost_without_asahi)} without
                </p>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <TrendingDown className="h-3.5 w-3.5" />
                  Savings
                </div>
                <p className="mt-1 text-sm font-medium text-green-400">
                  {formatCurrency(result.asahi.savings_usd)} ({result.asahi.savings_pct.toFixed(0)}%)
                </p>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" />
                  Tokens
                </div>
                <p className="mt-1 text-sm font-medium text-foreground">
                  {result.usage.total_tokens.toLocaleString()}
                </p>
                <p className="text-xs text-muted-foreground">
                  {result.usage.prompt_tokens} in / {result.usage.completion_tokens} out
                </p>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <Sparkles className="h-3.5 w-3.5" />
                  Routing
                </div>
                <p className="mt-1 text-sm font-medium text-foreground truncate">
                  {result.asahi.routing_reason}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
