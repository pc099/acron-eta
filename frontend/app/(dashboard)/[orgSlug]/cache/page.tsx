"use client";

import { useQuery } from "@tanstack/react-query";
import { getCachePerformance } from "@/lib/api";
import { cn, formatPercent } from "@/lib/utils";
import { Database, Layers, Brain, GitBranch } from "lucide-react";

const tierConfig = {
  exact: {
    label: "Exact Match",
    description: "Identical prompts served from cache",
    icon: Layers,
    color: "text-green-400",
    bgColor: "bg-green-500/20",
    barColor: "bg-green-400",
  },
  semantic: {
    label: "Semantic Match",
    description: "Semantically similar prompts served from cache",
    icon: Brain,
    color: "text-blue-400",
    bgColor: "bg-blue-500/20",
    barColor: "bg-blue-400",
  },
  intermediate: {
    label: "Intermediate",
    description: "Partial computations reused across requests",
    icon: GitBranch,
    color: "text-purple-400",
    bgColor: "bg-purple-500/20",
    barColor: "bg-purple-400",
  },
} as const;

export default function CachePage({
  params,
}: {
  params: { orgSlug: string };
}) {
  const { data: cache, isLoading } = useQuery({
    queryKey: ["cache-performance", params.orgSlug],
    queryFn: () => getCachePerformance("30d"),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Cache</h1>
        <p className="text-sm text-muted-foreground">
          Monitor cache performance across all tiers
        </p>
      </div>

      {isLoading ? (
        <div className="space-y-6">
          {/* Overall skeleton */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="animate-pulse space-y-4">
              <div className="h-6 w-40 rounded bg-muted" />
              <div className="h-16 w-full rounded bg-muted" />
            </div>
          </div>
          {/* Tier skeletons */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-lg border border-border bg-card p-6 shadow-sm">
                <div className="animate-pulse space-y-4">
                  <div className="h-5 w-32 rounded bg-muted" />
                  <div className="h-10 w-24 rounded bg-muted" />
                  <div className="h-4 w-full rounded bg-muted" />
                  <div className="h-3 w-20 rounded bg-muted" />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : !cache ? (
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <div className="flex h-48 items-center justify-center text-sm text-muted-foreground">
            No cache performance data available. Make some requests to start tracking cache metrics.
          </div>
        </div>
      ) : (
        <>
          {/* Overall hit rate */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-asahi/20">
                <Database className="h-5 w-5 text-asahi" />
              </div>
              <div>
                <p className="text-sm font-medium text-muted-foreground">
                  Overall Cache Hit Rate
                </p>
                <p className="text-3xl font-bold text-asahi">
                  {formatPercent(cache.cache_hit_rate * 100)}
                </p>
              </div>
            </div>
            <div className="mt-4">
              <div className="h-3 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-3 rounded-full bg-asahi transition-all duration-500"
                  style={{ width: `${cache.cache_hit_rate * 100}%` }}
                />
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                {cache.total_requests.toLocaleString()} total requests
              </p>
            </div>
          </div>

          {/* Per-tier breakdown */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
            {(["exact", "semantic", "intermediate"] as const).map((tier) => {
              const config = tierConfig[tier];
              const tierData = cache.tiers[tier];
              const Icon = config.icon;
              const ratePct = tierData.rate * 100;

              return (
                <div
                  key={tier}
                  className="rounded-lg border border-border bg-card p-6 shadow-sm"
                >
                  <div className="flex items-center gap-3">
                    <div className={cn("flex h-9 w-9 items-center justify-center rounded-lg", config.bgColor)}>
                      <Icon className={cn("h-4 w-4", config.color)} />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-foreground">
                        {config.label}
                      </h3>
                      <p className="text-xs text-muted-foreground">
                        {config.description}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4">
                    <p className={cn("text-2xl font-bold", config.color)}>
                      {tierData.hits.toLocaleString()}
                    </p>
                    <p className="text-xs text-muted-foreground">cache hits</p>
                  </div>

                  <div className="mt-4">
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-muted-foreground">Hit Rate</span>
                      <span className={cn("font-medium", config.color)}>
                        {formatPercent(ratePct)}
                      </span>
                    </div>
                    <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className={cn("h-2 rounded-full transition-all duration-500", config.barColor)}
                        style={{ width: `${ratePct}%` }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
