"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { fetchApi } from "@/lib/api";
import { Activity, AlertTriangle, CheckCircle, XCircle, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

interface CircuitBreakerInfo {
  state: "CLOSED" | "HALF_OPEN" | "OPEN";
  failure_count: number;
  recovery_remaining_seconds: number;
}

interface ProviderHealth {
  provider: string;
  health: "healthy" | "degraded" | "unreachable";
  circuit_breaker: CircuitBreakerInfo;
  timestamp: string;
}

interface ProviderHealthResponse {
  providers: ProviderHealth[];
  total_providers: number;
  healthy_count: number;
  degraded_count: number;
  unreachable_count: number;
}

function CircuitStateTag({ state }: { state: string }) {
  const colors = {
    CLOSED: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    HALF_OPEN: "bg-yellow-500/10 text-yellow-400 border-yellow-500/30",
    OPEN: "bg-red-500/10 text-red-400 border-red-500/30",
  };

  return (
    <span className={cn(
      "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium",
      colors[state as keyof typeof colors] || "bg-muted text-muted-foreground"
    )}>
      {state}
    </span>
  );
}

function HealthBadge({ health }: { health: string }) {
  const config = {
    healthy: {
      icon: CheckCircle,
      color: "text-emerald-400",
      bg: "bg-emerald-500/10",
    },
    degraded: {
      icon: AlertTriangle,
      color: "text-yellow-400",
      bg: "bg-yellow-500/10",
    },
    unreachable: {
      icon: XCircle,
      color: "text-red-400",
      bg: "bg-red-500/10",
    },
  };

  const { icon: Icon, color, bg } = config[health as keyof typeof config] || config.unreachable;

  return (
    <div className={cn("flex items-center gap-2 rounded-md px-3 py-1.5", bg)}>
      <Icon className={cn("h-4 w-4", color)} />
      <span className={cn("text-sm font-medium capitalize", color)}>{health}</span>
    </div>
  );
}

export default function ProvidersPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : "";

  const { data, isLoading, error, refetch, isRefetching } = useQuery<ProviderHealthResponse>({
    queryKey: ["provider-health", orgSlug],
    queryFn: () => fetchApi<ProviderHealthResponse>("/providers/health", { orgSlug }),
    enabled: !!orgSlug,
    refetchInterval: 30000, // Auto-refresh every 30 seconds
  });

  if (isLoading) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Provider Health</h1>
          <p className="text-sm text-muted-foreground">
            Real-time health monitoring and circuit breaker status for all configured providers.
          </p>
        </div>
        <div className="animate-pulse space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 w-full rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Provider Health</h1>
          <p className="text-sm text-muted-foreground">
            Real-time health monitoring and circuit breaker status for all configured providers.
          </p>
        </div>
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <XCircle className="h-12 w-12 text-red-400/50 mb-4" />
          <p className="text-sm text-muted-foreground">Failed to load provider health data.</p>
          <button
            onClick={() => refetch()}
            className="mt-4 rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white hover:bg-asahio/90 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  const providers = data?.providers || [];
  const stats = {
    total: data?.total_providers || 0,
    healthy: data?.healthy_count || 0,
    degraded: data?.degraded_count || 0,
    unreachable: data?.unreachable_count || 0,
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Provider Health</h1>
          <p className="text-sm text-muted-foreground">
            Real-time health monitoring and circuit breaker status for all configured providers.
          </p>
        </div>
        <button
          onClick={() => refetch()}
          disabled={isRefetching}
          className={cn(
            "flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted",
            isRefetching && "opacity-50 cursor-not-allowed"
          )}
        >
          <RefreshCw className={cn("h-4 w-4", isRefetching && "animate-spin")} />
          Refresh
        </button>
      </div>

      {/* Stats Overview */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-asahio" />
            <h3 className="text-sm font-medium text-muted-foreground">Total Providers</h3>
          </div>
          <p className="mt-2 text-3xl font-bold text-foreground">{stats.total}</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <CheckCircle className="h-4 w-4 text-emerald-400" />
            <h3 className="text-sm font-medium text-muted-foreground">Healthy</h3>
          </div>
          <p className="mt-2 text-3xl font-bold text-emerald-400">{stats.healthy}</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-yellow-400" />
            <h3 className="text-sm font-medium text-muted-foreground">Degraded</h3>
          </div>
          <p className="mt-2 text-3xl font-bold text-yellow-400">{stats.degraded}</p>
        </div>

        <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
          <div className="flex items-center gap-2">
            <XCircle className="h-4 w-4 text-red-400" />
            <h3 className="text-sm font-medium text-muted-foreground">Unreachable</h3>
          </div>
          <p className="mt-2 text-3xl font-bold text-red-400">{stats.unreachable}</p>
        </div>
      </div>

      {/* Provider Cards */}
      {providers.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <Activity className="h-12 w-12 text-muted-foreground/50 mb-4" />
          <p className="text-sm text-muted-foreground">No providers configured yet.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {providers.map((provider) => (
            <div
              key={provider.provider}
              className="rounded-lg border border-border bg-card p-5 shadow-sm hover:shadow-md transition-shadow"
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h3 className="text-lg font-semibold text-foreground capitalize">
                    {provider.provider}
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    Updated {new Date(provider.timestamp).toLocaleTimeString()}
                  </p>
                </div>
                <HealthBadge health={provider.health} />
              </div>

              <div className="space-y-3">
                {/* Circuit Breaker Status */}
                <div className="rounded-md bg-muted/30 p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-medium text-muted-foreground">Circuit Breaker</span>
                    <CircuitStateTag state={provider.circuit_breaker.state} />
                  </div>

                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-muted-foreground">Failure Count:</span>
                      <p className="font-mono text-foreground mt-1">
                        {provider.circuit_breaker.failure_count}
                      </p>
                    </div>

                    {provider.circuit_breaker.state === "OPEN" && (
                      <div>
                        <span className="text-muted-foreground">Recovery In:</span>
                        <p className="font-mono text-foreground mt-1">
                          {Math.max(0, provider.circuit_breaker.recovery_remaining_seconds).toFixed(1)}s
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Status Message */}
                {provider.health === "degraded" && (
                  <div className="flex items-start gap-2 rounded-md bg-yellow-500/10 border border-yellow-500/30 p-3">
                    <AlertTriangle className="h-4 w-4 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div className="text-xs text-yellow-300">
                      <p className="font-medium">Degraded Performance</p>
                      <p className="text-yellow-400/90 mt-1">
                        This provider is experiencing elevated error rates or latency.
                      </p>
                    </div>
                  </div>
                )}

                {provider.health === "unreachable" && (
                  <div className="flex items-start gap-2 rounded-md bg-red-500/10 border border-red-500/30 p-3">
                    <XCircle className="h-4 w-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <div className="text-xs text-red-300">
                      <p className="font-medium">Provider Unreachable</p>
                      <p className="text-red-400/90 mt-1">
                        This provider is not responding. Requests will be routed to healthy providers.
                      </p>
                    </div>
                  </div>
                )}

                {provider.circuit_breaker.state === "OPEN" && (
                  <div className="flex items-start gap-2 rounded-md bg-red-500/10 border border-red-500/30 p-3">
                    <XCircle className="h-4 w-4 text-red-400 flex-shrink-0 mt-0.5" />
                    <div className="text-xs text-red-300">
                      <p className="font-medium">Circuit Breaker Open</p>
                      <p className="text-red-400/90 mt-1">
                        Circuit opened due to consecutive failures. Will retry in {Math.max(0, provider.circuit_breaker.recovery_remaining_seconds).toFixed(1)}s.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded-lg border border-border bg-muted/30 p-4 text-xs text-muted-foreground">
        <p className="flex items-center gap-2">
          <Activity className="h-3 w-3" />
          <span>
            Provider health is monitored every 60 seconds. Circuit breakers automatically open after 3 consecutive failures
            and will attempt recovery after 30 seconds.
          </span>
        </p>
      </div>
    </div>
  );
}
