"use client";

import { useQuery } from "@tanstack/react-query";
import {
  getAnalyticsOverview,
  getSavingsTimeSeries,
  getModelBreakdown,
  getRequestLogs,
} from "@/lib/api";
import { KpiCard } from "@/components/charts/kpi-card";
import { SavingsChart } from "@/components/charts/savings-chart";
import { ModelDistributionChart } from "@/components/charts/model-distribution-chart";
import { RecentRequestsTable } from "@/components/charts/recent-requests-table";
import {
  DollarSign,
  Activity,
  Database,
  TrendingUp,
} from "lucide-react";

export default function DashboardPage({
  params,
}: {
  params: { orgSlug: string };
}) {
  const { data: overview, isLoading: overviewLoading } = useQuery({
    queryKey: ["overview", params.orgSlug],
    queryFn: () => getAnalyticsOverview("30d"),
  });

  const { data: savings } = useQuery({
    queryKey: ["savings", params.orgSlug],
    queryFn: () => getSavingsTimeSeries("30d", "day"),
  });

  const { data: models } = useQuery({
    queryKey: ["models", params.orgSlug],
    queryFn: () => getModelBreakdown("30d"),
  });

  const { data: requests } = useQuery({
    queryKey: ["recent-requests", params.orgSlug],
    queryFn: () => getRequestLogs({ limit: 10 }),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Monitor your ASAHI optimization metrics
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          title="Total Savings"
          value={overview?.total_savings_usd ?? 0}
          format="currency"
          delta={overview?.savings_delta_pct}
          deltaLabel="vs last period"
          icon={DollarSign}
          loading={overviewLoading}
          highlight
        />
        <KpiCard
          title="Total Requests"
          value={overview?.total_requests ?? 0}
          format="number"
          delta={overview?.requests_delta_pct}
          deltaLabel="vs last period"
          icon={Activity}
          loading={overviewLoading}
        />
        <KpiCard
          title="Cache Hit Rate"
          value={(overview?.cache_hit_rate ?? 0) * 100}
          format="percentage"
          icon={Database}
          loading={overviewLoading}
        />
        <KpiCard
          title="Avg Latency"
          value={overview?.avg_latency_ms ?? 0}
          format="number"
          suffix="ms"
          icon={TrendingUp}
          loading={overviewLoading}
        />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <SavingsChart data={savings?.data ?? []} />
        <ModelDistributionChart data={models?.data ?? []} />
      </div>

      {/* Recent Requests */}
      <RecentRequestsTable
        data={requests?.data ?? []}
        orgSlug={params.orgSlug}
      />
    </div>
  );
}
