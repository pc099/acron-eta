"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getAnalyticsOverview,
  getSavingsTimeSeries,
  getModelBreakdown,
  getCachePerformance,
  getLatencyPercentiles,
  getForecast,
  getRecommendations,
} from "@/lib/api";
import { SavingsChart } from "@/components/charts/savings-chart";
import { ModelDistributionChart } from "@/components/charts/model-distribution-chart";
import { cn, formatCurrency, formatPercent } from "@/lib/utils";
import {
  DollarSign,
  Activity,
  Database,
  TrendingUp,
  TrendingDown,
  Lightbulb,
  BarChart3,
  Zap,
} from "lucide-react";

const PERIODS = [
  { label: "7d", value: "7d" },
  { label: "30d", value: "30d" },
  { label: "90d", value: "90d" },
] as const;

const IMPACT_STYLES: Record<string, string> = {
  high: "border-asahi/30 bg-asahi/5",
  medium: "border-blue-500/30 bg-blue-500/5",
  low: "border-muted-foreground/20 bg-muted/5",
};

const IMPACT_BADGE: Record<string, string> = {
  high: "bg-asahi/20 text-asahi",
  medium: "bg-blue-500/20 text-blue-400",
  low: "bg-muted text-muted-foreground",
};

export default function AnalyticsPage({
  params,
}: {
  params: { orgSlug: string };
}) {
  const [period, setPeriod] = useState("30d");

  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["analytics-overview", params.orgSlug, period],
    queryFn: () => getAnalyticsOverview(period),
  });

  const { data: savings } = useQuery({
    queryKey: ["analytics-savings", params.orgSlug, period],
    queryFn: () => getSavingsTimeSeries(period, "day"),
  });

  const { data: models } = useQuery({
    queryKey: ["analytics-models", params.orgSlug, period],
    queryFn: () => getModelBreakdown(period),
  });

  const { data: cache, isLoading: cacheLoading } = useQuery({
    queryKey: ["analytics-cache", params.orgSlug, period],
    queryFn: () => getCachePerformance(period),
  });

  const { data: latency, isLoading: latencyLoading } = useQuery({
    queryKey: ["analytics-latency", params.orgSlug, period],
    queryFn: () => getLatencyPercentiles(period),
  });

  const { data: forecast, isLoading: forecastLoading } = useQuery({
    queryKey: ["analytics-forecast", params.orgSlug],
    queryFn: () => getForecast(30),
  });

  const { data: recommendationsData, isLoading: recommendationsLoading } = useQuery({
    queryKey: ["analytics-recommendations", params.orgSlug],
    queryFn: () => getRecommendations(),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Analytics</h1>
          <p className="text-sm text-muted-foreground">
            Deep dive into your ASAHI optimization performance
          </p>
        </div>

        {/* Period selector */}
        <div className="flex items-center gap-1 rounded-md border border-border bg-background p-1">
          {PERIODS.map((p) => (
            <button
              key={p.value}
              onClick={() => setPeriod(p.value)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                period === p.value
                  ? "bg-asahi text-white"
                  : "text-muted-foreground hover:text-foreground"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {overviewLoading ? (
          [1, 2, 3, 4].map((i) => (
            <div key={i} className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="animate-pulse space-y-3">
                <div className="h-4 w-24 rounded bg-muted" />
                <div className="h-8 w-32 rounded bg-muted" />
              </div>
            </div>
          ))
        ) : (
          <>
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">Total Savings</p>
                <DollarSign className="h-4 w-4 text-asahi" />
              </div>
              <p className="mt-2 text-2xl font-bold text-asahi">
                {formatCurrency(overview?.total_savings_usd ?? 0)}
              </p>
              {overview && overview.savings_delta_pct !== 0 && (
                <p className={cn(
                  "mt-1 text-xs font-medium",
                  overview.savings_delta_pct > 0 ? "text-green-400" : "text-red-400"
                )}>
                  {overview.savings_delta_pct > 0 ? "+" : ""}{overview.savings_delta_pct.toFixed(1)}% vs prev period
                </p>
              )}
            </div>
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">Avg Savings</p>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="mt-2 text-2xl font-bold text-foreground">
                {formatPercent(overview?.average_savings_pct ?? 0)}
              </p>
            </div>
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">Total Requests</p>
                <Activity className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="mt-2 text-2xl font-bold text-foreground">
                {(overview?.total_requests ?? 0).toLocaleString()}
              </p>
              {overview && overview.requests_delta_pct !== 0 && (
                <p className={cn(
                  "mt-1 text-xs font-medium",
                  overview.requests_delta_pct > 0 ? "text-green-400" : "text-red-400"
                )}>
                  {overview.requests_delta_pct > 0 ? "+" : ""}{overview.requests_delta_pct.toFixed(1)}% vs prev period
                </p>
              )}
            </div>
            <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium text-muted-foreground">Cache Hit Rate</p>
                <Database className="h-4 w-4 text-muted-foreground" />
              </div>
              <p className="mt-2 text-2xl font-bold text-foreground">
                {formatPercent((overview?.cache_hit_rate ?? 0) * 100)}
              </p>
            </div>
          </>
        )}
      </div>

      {/* Savings chart + Model breakdown */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SavingsChart data={savings?.data ?? []} />
        <ModelDistributionChart data={models?.data ?? []} />
      </div>

      {/* Forecast */}
      <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <BarChart3 className="h-4 w-4 text-asahi" />
          <h3 className="text-sm font-semibold text-foreground">
            30-Day Forecast
          </h3>
        </div>
        {forecastLoading ? (
          <div className="animate-pulse space-y-3">
            <div className="h-6 w-48 rounded bg-muted" />
            <div className="h-4 w-full rounded bg-muted" />
          </div>
        ) : !forecast ? (
          <div className="flex h-20 items-center justify-center text-sm text-muted-foreground">
            Not enough data for forecasting yet. Send more requests to generate projections.
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs text-muted-foreground">Projected Cost</p>
              <p className="mt-1 text-lg font-bold text-foreground">
                {formatCurrency(forecast.projected_cost_usd)}
              </p>
              <p className="text-xs text-muted-foreground">
                ~{formatCurrency(forecast.daily_avg_cost)}/day
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Projected Savings</p>
              <p className="mt-1 text-lg font-bold text-green-400">
                {formatCurrency(forecast.projected_savings_usd)}
              </p>
              <p className="text-xs text-muted-foreground">
                ~{formatCurrency(forecast.daily_avg_savings)}/day
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Projected Requests</p>
              <p className="mt-1 text-lg font-bold text-foreground">
                {forecast.projected_requests.toLocaleString()}
              </p>
            </div>
            <div>
              <p className="text-xs text-muted-foreground">Efficiency Ratio</p>
              <p className="mt-1 text-lg font-bold text-asahi">
                {forecast.projected_cost_usd > 0
                  ? formatPercent(
                      (forecast.projected_savings_usd /
                        (forecast.projected_cost_usd + forecast.projected_savings_usd)) *
                        100
                    )
                  : "N/A"}
              </p>
              <p className="text-xs text-muted-foreground">savings / total spend</p>
            </div>
          </div>
        )}
      </div>

      {/* Cache performance + Latency percentiles */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Cache performance */}
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold text-foreground">
            Cache Performance
          </h3>
          {cacheLoading ? (
            <div className="animate-pulse space-y-3">
              <div className="h-6 w-40 rounded bg-muted" />
              <div className="h-4 w-full rounded bg-muted" />
              <div className="h-4 w-full rounded bg-muted" />
              <div className="h-4 w-full rounded bg-muted" />
            </div>
          ) : !cache ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              No cache data available.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Overall Hit Rate</span>
                <span className="text-lg font-bold text-asahi">
                  {formatPercent(cache.cache_hit_rate * 100)}
                </span>
              </div>
              <div className="h-px bg-border" />
              {(["exact", "semantic", "intermediate"] as const).map((tier) => {
                const maxHits = Math.max(
                  cache.tiers.exact.hits,
                  cache.tiers.semantic.hits,
                  cache.tiers.intermediate.hits,
                  1
                );
                const widthPct = (cache.tiers[tier].hits / maxHits) * 100;
                return (
                  <div key={tier}>
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <div
                          className={cn(
                            "h-2 w-2 rounded-full",
                            tier === "exact"
                              ? "bg-green-400"
                              : tier === "semantic"
                                ? "bg-blue-400"
                                : "bg-purple-400"
                          )}
                        />
                        <span className="text-sm capitalize text-foreground">{tier}</span>
                      </div>
                      <div className="text-right">
                        <span className="text-sm font-medium text-foreground">
                          {cache.tiers[tier].hits.toLocaleString()} hits
                        </span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          ({formatPercent(cache.tiers[tier].rate * 100)})
                        </span>
                      </div>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted">
                      <div
                        className={cn(
                          "h-1.5 rounded-full transition-all",
                          tier === "exact"
                            ? "bg-green-400"
                            : tier === "semantic"
                              ? "bg-blue-400"
                              : "bg-purple-400"
                        )}
                        style={{ width: `${widthPct}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Latency percentiles */}
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h3 className="mb-4 text-sm font-semibold text-foreground">
            Latency Percentiles
          </h3>
          {latencyLoading ? (
            <div className="animate-pulse space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-8 rounded bg-muted" />
              ))}
            </div>
          ) : !latency ? (
            <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
              No latency data available.
            </div>
          ) : (
            <div className="space-y-3">
              {(
                [
                  { label: "Average", key: "avg" },
                  { label: "p50", key: "p50" },
                  { label: "p90", key: "p90" },
                  { label: "p95", key: "p95" },
                  { label: "p99", key: "p99" },
                ] as const
              ).map(({ label, key }) => {
                const value = latency[key];
                const maxMs = latency.p99 || 1;
                const widthPct = Math.min((value / maxMs) * 100, 100);
                return (
                  <div key={key} className="flex items-center gap-4">
                    <span className="w-16 text-sm text-muted-foreground">{label}</span>
                    <div className="flex-1">
                      <div className="h-6 rounded bg-muted">
                        <div
                          className="flex h-6 items-center rounded bg-asahi/20"
                          style={{ width: `${widthPct}%` }}
                        >
                          <span className="px-2 text-xs font-medium text-foreground">
                            {value.toFixed(0)}ms
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Recommendations */}
      <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <Lightbulb className="h-4 w-4 text-asahi" />
          <h3 className="text-sm font-semibold text-foreground">
            Optimization Recommendations
          </h3>
        </div>
        {recommendationsLoading ? (
          <div className="animate-pulse space-y-3">
            <div className="h-20 rounded bg-muted" />
            <div className="h-20 rounded bg-muted" />
          </div>
        ) : !recommendationsData ||
          recommendationsData.recommendations.length === 0 ? (
          <div className="flex items-center gap-3 rounded-md border border-green-500/30 bg-green-500/5 p-4">
            <Zap className="h-5 w-5 text-green-400" />
            <div>
              <p className="text-sm font-medium text-foreground">
                All optimized
              </p>
              <p className="text-xs text-muted-foreground">
                No recommendations right now — your setup is performing well.
              </p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {recommendationsData.recommendations.map((rec, i) => (
              <div
                key={i}
                className={cn(
                  "rounded-md border p-4",
                  IMPACT_STYLES[rec.impact] || IMPACT_STYLES.low
                )}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-foreground">
                        {rec.title}
                      </p>
                      <span
                        className={cn(
                          "rounded-full px-2 py-0.5 text-[10px] font-medium uppercase",
                          IMPACT_BADGE[rec.impact] || IMPACT_BADGE.low
                        )}
                      >
                        {rec.impact} impact
                      </span>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                      {rec.description}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
