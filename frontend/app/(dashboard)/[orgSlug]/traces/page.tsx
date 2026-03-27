"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getRequestLogs,
  listSessions,
  getSessionGraph,
  tagHallucination,
  type RequestLogEntry,
  type SessionItem,
  type SessionGraphResponse,
} from "@/lib/api";
import { Activity, AlertTriangle, ChevronDown, ChevronRight, Database, GitBranch, Layers, Radio, Shield, Zap } from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";

const INTERVENTION_LABELS: Record<number, string> = {
  0: "LOG",
  1: "FLAG",
  2: "AUGMENT",
  3: "REROUTE",
  4: "BLOCK",
};

function RiskBadge({ score }: { score: number }) {
  let color = "bg-green-500/10 text-green-400";
  if (score >= 0.7) color = "bg-red-500/10 text-red-400";
  else if (score >= 0.5) color = "bg-orange-500/10 text-orange-400";
  else if (score >= 0.3) color = "bg-yellow-500/10 text-yellow-400";
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${color}`}>
      {score.toFixed(3)}
    </span>
  );
}

function InterventionLabel({ level }: { level: number }) {
  const label = INTERVENTION_LABELS[level] ?? `L${level}`;
  const colors: Record<number, string> = {
    1: "text-yellow-400",
    2: "text-blue-400",
    3: "text-orange-400",
    4: "text-red-400",
  };
  return <span className={`text-xs font-medium ${colors[level] ?? "text-muted-foreground"}`}>{label}</span>;
}

type Tab = "traces" | "sessions" | "live";

interface LiveTrace {
  id: string;
  agent_id?: string | null;
  model_used?: string | null;
  provider?: string | null;
  routing_mode?: string | null;
  cache_hit?: boolean;
  cache_tier?: string | null;
  input_tokens?: number;
  output_tokens?: number;
  latency_ms?: number | null;
  risk_score?: number | null;
  intervention_level?: number | null;
  savings_usd?: number;
  received_at: string;
}

function SessionGraphPanel({ graph }: { graph: SessionGraphResponse }) {
  if (graph.step_count === 0) {
    return (
      <p className="text-sm text-muted-foreground">No steps recorded for this session.</p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <GitBranch className="h-4 w-4 text-asahio" />
        <h3 className="text-sm font-semibold text-foreground">
          Session Graph ({graph.step_count} steps)
        </h3>
      </div>
      <div className="space-y-2">
        {graph.steps.map((step) => (
          <div
            key={step.step_number}
            className="flex items-start gap-3 rounded-md border border-border bg-muted/30 p-3"
          >
            <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-asahio/20 text-xs font-bold text-asahio">
              {step.step_number}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-foreground">{step.model_used}</span>
                {step.cache_hit && (
                  <span className="rounded-full bg-green-500/20 px-2 py-0.5 text-xs text-green-400">
                    cached
                  </span>
                )}
                {step.latency_ms != null && (
                  <span className="text-xs text-muted-foreground">{step.latency_ms}ms</span>
                )}
              </div>
              {step.depends_on.length > 0 && (
                <p className="mt-1 text-xs text-muted-foreground">
                  depends on: {step.depends_on.map((d) => `step ${d}`).join(", ")}
                </p>
              )}
            </div>
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {step.created_at
                ? new Date(step.created_at).toLocaleTimeString(undefined, {
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  })
                : ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function TracesPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : "";

  const [tab, setTab] = useState<Tab>("traces");
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [filterCacheHit, setFilterCacheHit] = useState<boolean | undefined>(undefined);
  const [selectedSession, setSelectedSession] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["traces", orgSlug, page, filterCacheHit],
    queryFn: () =>
      getRequestLogs(
        { page, limit: 25, cache_hit: filterCacheHit },
        undefined,
        orgSlug,
      ),
    enabled: !!orgSlug && tab === "traces",
  });

  const { data: sessionsData, isLoading: sessionsLoading } = useQuery({
    queryKey: ["sessions", orgSlug],
    queryFn: () => listSessions({ limit: 50 }, undefined, orgSlug),
    enabled: Boolean(orgSlug) && tab === "sessions",
  });

  const { data: graphData, isLoading: graphLoading } = useQuery({
    queryKey: ["session-graph", orgSlug, selectedSession],
    queryFn: () => getSessionGraph(selectedSession!, undefined, orgSlug),
    enabled: Boolean(orgSlug) && Boolean(selectedSession),
  });

  const logs = data?.data ?? [];
  const pagination = data?.pagination;
  const sessions = sessionsData?.data ?? [];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Traces & Sessions</h1>
          <p className="text-sm text-muted-foreground">
            Inspect individual inference calls, latency, cost, and cache behavior.
          </p>
        </div>
        {tab === "traces" && (
          <div className="flex items-center gap-2">
            <select
              value={filterCacheHit === undefined ? "all" : filterCacheHit ? "hits" : "misses"}
              onChange={(e) => {
                const v = e.target.value;
                setFilterCacheHit(v === "all" ? undefined : v === "hits");
                setPage(1);
              }}
              className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground"
            >
              <option value="all">All requests</option>
              <option value="hits">Cache hits</option>
              <option value="misses">Cache misses</option>
            </select>
          </div>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 rounded-lg bg-muted p-1">
        {(
          [
            { key: "traces" as const, label: "Call Traces", icon: Activity },
            { key: "live" as const, label: "Live", icon: Radio },
            { key: "sessions" as const, label: "Sessions", icon: Layers },
          ]
        ).map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => {
              setTab(key);
              setSelectedSession(null);
            }}
            className={cn(
              "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
              tab === key
                ? "bg-card text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      {/* Sessions tab */}
      {tab === "sessions" && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-border bg-card shadow-sm overflow-x-auto">
            {sessionsLoading ? (
              <div className="p-6 animate-pulse space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-10 w-full rounded bg-muted" />
                ))}
              </div>
            ) : sessions.length === 0 ? (
              <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
                No sessions recorded yet. Sessions are created when agents send a session_id.
              </div>
            ) : (
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border bg-muted/50">
                    <th className="px-4 py-3 text-xs font-medium text-muted-foreground">Session</th>
                    <th className="px-4 py-3 text-xs font-medium text-muted-foreground">Agent</th>
                    <th className="px-4 py-3 text-xs font-medium text-muted-foreground">Traces</th>
                    <th className="px-4 py-3 text-xs font-medium text-muted-foreground">Started</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {sessions.map((s) => (
                    <tr
                      key={s.id}
                      className={cn(
                        "cursor-pointer transition-colors",
                        selectedSession === s.id ? "bg-asahio/10" : "hover:bg-muted/50"
                      )}
                      onClick={() => setSelectedSession(s.id)}
                    >
                      <td className="px-4 py-3 text-xs font-mono text-muted-foreground">
                        {s.id.slice(0, 8)}...
                      </td>
                      <td className="px-4 py-3 text-xs font-mono text-muted-foreground">
                        {s.agent_id.slice(0, 8)}...
                      </td>
                      <td className="px-4 py-3 tabular-nums">{s.trace_count}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {s.started_at
                          ? new Date(s.started_at).toLocaleString(undefined, {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "-"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            {!selectedSession ? (
              <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
                <div className="text-center">
                  <GitBranch className="mx-auto h-8 w-8 text-muted-foreground/50 mb-2" />
                  <p>Select a session to view its dependency graph</p>
                </div>
              </div>
            ) : graphLoading ? (
              <div className="animate-pulse space-y-3">
                <div className="h-5 w-40 rounded bg-muted" />
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-16 w-full rounded bg-muted" />
                ))}
              </div>
            ) : graphData ? (
              <SessionGraphPanel graph={graphData} />
            ) : (
              <p className="text-sm text-muted-foreground">Failed to load session graph.</p>
            )}
          </div>
        </div>
      )}

      {/* Live tab */}
      {tab === "live" && <LiveTracePanel orgSlug={orgSlug} />}

      {/* Traces tab */}
      {tab === "traces" && (
        isLoading ? (
          <div className="flex items-center justify-center py-12 text-muted-foreground">Loading traces...</div>
        ) : logs.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
            <Activity className="h-12 w-12 text-muted-foreground/50" />
            <p className="mt-4 text-sm text-muted-foreground">No traces found.</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/50">
                  <tr>
                    <th className="w-8 px-2 py-3"></th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Time</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Model</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Provider</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Routing</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Tokens</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Latency</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Cache</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Risk</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Intervention</th>
                    <th className="px-4 py-3 font-medium text-muted-foreground">Savings</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {logs.map((log) => (
                    <TraceRow
                      key={log.id}
                      log={log}
                      expanded={expandedId === log.id}
                      onToggle={() => setExpandedId(expandedId === log.id ? null : log.id)}
                      orgSlug={orgSlug}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            {pagination && pagination.pages > 1 && (
              <div className="flex items-center justify-between text-sm text-muted-foreground">
                <span>
                  Page {pagination.page} of {pagination.pages} ({pagination.total} total)
                </span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="rounded-md border border-border px-3 py-1 text-foreground transition-colors hover:bg-muted disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() => setPage((p) => p + 1)}
                    disabled={page >= pagination.pages}
                    className="rounded-md border border-border px-3 py-1 text-foreground transition-colors hover:bg-muted disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )
      )}
    </div>
  );
}

function HallucinationTagButton({ traceId, orgSlug }: { traceId: string; orgSlug: string }) {
  const queryClient = useQueryClient();
  const [tagged, setTagged] = useState(false);

  const mutation = useMutation({
    mutationFn: (detected: boolean) =>
      tagHallucination(traceId, { hallucination_detected: detected }, undefined, orgSlug),
    onSuccess: (data) => {
      setTagged(data.hallucination_detected);
      queryClient.invalidateQueries({ queryKey: ["traces"] });
    },
    onError: (error) => {
      console.error("Failed to tag hallucination:", error);
      alert("Failed to tag hallucination. Please try again.");
    },
  });

  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        mutation.mutate(!tagged);
      }}
      disabled={mutation.isPending}
      title={mutation.isError ? "Failed to tag - click to retry" : undefined}
      className={cn(
        "flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
        mutation.isError && "border-red-500 bg-red-500/20",
        tagged
          ? "border-red-500/50 bg-red-500/10 text-red-400 hover:bg-red-500/20"
          : "border-border bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
      )}
    >
      <AlertTriangle className="h-3 w-3" />
      {mutation.isPending ? "..." : mutation.isError ? "Error" : tagged ? "Hallucination" : "Mark Hallucination"}
    </button>
  );
}

function LiveTracePanel({ orgSlug }: { orgSlug: string }) {
  const [traces, setTraces] = useState<LiveTrace[]>([]);
  const [status, setStatus] = useState<"connecting" | "connected" | "error">("connecting");
  const [paused, setPaused] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  const apiBase = (
    process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"
  ).replace(/\/$/, "");

  useEffect(() => {
    // Get API key from localStorage
    const apiKey = localStorage.getItem("asahio_api_key");
    if (!apiKey) {
      setStatus("error");
      console.error("No API key found in localStorage");
      return;
    }

    // EventSource doesn't support custom headers, so we pass the token as a query param
    const url = `${apiBase}/traces/live?token=${encodeURIComponent(apiKey)}`;
    const es = new EventSource(url);
    esRef.current = es;

    es.addEventListener("connected", () => setStatus("connected"));

    es.onmessage = (event) => {
      if (pausedRef.current) return;
      try {
        const data = JSON.parse(event.data) as LiveTrace;
        data.received_at = new Date().toISOString();
        setTraces((prev) => [data, ...prev].slice(0, 200));
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      setStatus("error");
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [apiBase, orgSlug]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              "h-2 w-2 rounded-full",
              status === "connected"
                ? "bg-emerald-400 animate-pulse"
                : status === "connecting"
                ? "bg-yellow-400 animate-pulse"
                : "bg-red-400"
            )}
          />
          <span className="text-sm text-muted-foreground">
            {status === "connected"
              ? `Live — ${traces.length} events`
              : status === "connecting"
              ? "Connecting..."
              : "Disconnected"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaused((p) => !p)}
            className={cn(
              "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
              paused
                ? "border-amber-500/50 bg-amber-500/10 text-amber-400"
                : "border-border bg-muted text-muted-foreground hover:text-foreground"
            )}
          >
            {paused ? "Resume" : "Pause"}
          </button>
          <button
            onClick={() => setTraces([])}
            className="rounded-md border border-border bg-muted px-3 py-1.5 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            Clear
          </button>
        </div>
      </div>

      {traces.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16">
          <Radio className="h-10 w-10 text-muted-foreground/50 animate-pulse" />
          <p className="mt-4 text-sm text-muted-foreground">
            Waiting for live traces... Send requests through the gateway to see them here.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Time</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Model</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Provider</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Routing</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Tokens</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Latency</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Cache</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {traces.map((t, i) => (
                <tr
                  key={`${t.id}-${i}`}
                  className="animate-fade-in transition-colors hover:bg-muted/30"
                >
                  <td className="px-4 py-3 text-muted-foreground whitespace-nowrap text-xs">
                    {new Date(t.received_at).toLocaleTimeString(undefined, {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-foreground">
                    {t.model_used ?? "-"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {t.provider ?? "-"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {t.routing_mode ?? "-"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {(t.input_tokens ?? 0) + (t.output_tokens ?? 0)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground text-xs">
                    {t.latency_ms != null ? `${t.latency_ms}ms` : "-"}
                  </td>
                  <td className="px-4 py-3">
                    {t.cache_hit ? (
                      <span className="flex items-center gap-1 text-xs text-emerald-400">
                        <Database className="h-3 w-3" />
                        {t.cache_tier ?? "hit"}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Zap className="h-3 w-3" /> miss
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {t.risk_score != null ? (
                      <RiskBadge score={t.risk_score} />
                    ) : (
                      <span className="text-muted-foreground text-xs">-</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TraceRow({
  log,
  expanded,
  onToggle,
  orgSlug,
}: {
  log: RequestLogEntry;
  expanded: boolean;
  onToggle: () => void;
  orgSlug: string;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer hover:bg-muted/30 transition-colors"
      >
        <td className="px-2 py-3 text-muted-foreground">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </td>
        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
          {new Date(log.created_at).toLocaleString()}
        </td>
        <td className="px-4 py-3 font-mono text-xs text-foreground">{log.model_used}</td>
        <td className="px-4 py-3 text-muted-foreground">{log.provider ?? "-"}</td>
        <td className="px-4 py-3 text-muted-foreground">{log.routing_mode ?? "-"}</td>
        <td className="px-4 py-3 text-muted-foreground">
          {log.input_tokens + log.output_tokens}
        </td>
        <td className="px-4 py-3 text-muted-foreground">
          {log.latency_ms != null ? `${log.latency_ms}ms` : "-"}
        </td>
        <td className="px-4 py-3">
          {log.cache_hit ? (
            <span className="flex items-center gap-1 text-emerald-400">
              <Database className="h-3 w-3" />
              {log.cache_tier ?? "hit"}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-muted-foreground">
              <Zap className="h-3 w-3" /> miss
            </span>
          )}
        </td>
        <td className="px-4 py-3">
          {log.risk_score != null ? (
            <RiskBadge score={log.risk_score} />
          ) : (
            <span className="text-muted-foreground">-</span>
          )}
        </td>
        <td className="px-4 py-3">
          {log.intervention_level != null && log.intervention_level > 0 ? (
            <InterventionLabel level={log.intervention_level} />
          ) : (
            <span className="text-muted-foreground">-</span>
          )}
        </td>
        <td className="px-4 py-3">
          {log.savings_usd > 0 ? (
            <span className="text-emerald-400">{formatCurrency(log.savings_usd)}</span>
          ) : (
            <span className="text-muted-foreground">-</span>
          )}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-muted/20">
          <td colSpan={11} className="px-8 py-4">
            <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
              <div>
                <span className="text-muted-foreground">Request ID</span>
                <p className="font-mono text-xs text-foreground">{log.request_id ?? log.id}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Model Requested</span>
                <p className="text-foreground">{log.model_requested ?? "auto"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Input Tokens</span>
                <p className="text-foreground">{log.input_tokens}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Output Tokens</span>
                <p className="text-foreground">{log.output_tokens}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Cost (without ASAHIO)</span>
                <p className="text-foreground">{formatCurrency(log.cost_without_asahi)}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Cost (with ASAHIO)</span>
                <p className="text-foreground">{formatCurrency(log.cost_with_asahi)}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Savings %</span>
                <p className="text-foreground">{log.savings_pct != null ? `${log.savings_pct.toFixed(1)}%` : "-"}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Status</span>
                <p className="text-foreground">{log.status_code}</p>
              </div>
              {log.risk_score != null && (
                <div>
                  <span className="text-muted-foreground">Risk Score</span>
                  <p className="text-foreground">{log.risk_score.toFixed(4)}</p>
                </div>
              )}
              {log.intervention_level != null && (
                <div>
                  <span className="text-muted-foreground">Intervention Level</span>
                  <p className="text-foreground">{INTERVENTION_LABELS[log.intervention_level] ?? `L${log.intervention_level}`}</p>
                </div>
              )}
            </div>
            {log.risk_factors && Object.keys(log.risk_factors).length > 0 && (
              <div className="mt-4 border-t border-border/50 pt-3">
                <span className="text-muted-foreground text-xs flex items-center gap-1 mb-2">
                  <Shield className="h-3 w-3" /> Risk Factors
                </span>
                <div className="flex flex-wrap gap-3">
                  {Object.entries(log.risk_factors).map(([factor, score]) => (
                    <div key={factor} className="text-xs">
                      <span className="text-muted-foreground">{factor}:</span>{" "}
                      <span className="font-mono text-foreground">{(score as number).toFixed(3)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            <div className="mt-4 border-t border-border/50 pt-3 flex items-center gap-3">
              <HallucinationTagButton traceId={log.id} orgSlug={orgSlug} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
