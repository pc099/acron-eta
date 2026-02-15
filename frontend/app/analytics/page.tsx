"use client";

import { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { Card } from "@/components/Card";
import { getCostBreakdown, getTrends, getCostSummary } from "@/lib/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Legend,
} from "recharts";

const ACRON_PRIMARY = "#FF6B35";

export default function AnalyticsPage() {
  const [period, setPeriod] = useState("day");
  const [breakdown, setBreakdown] = useState<unknown>(null);
  const [trends, setTrends] = useState<unknown>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [b, t, s] = await Promise.all([
          getCostBreakdown(period, "model"),
          getTrends("cost", period, 30),
          getCostSummary(period === "day" ? "24h" : period === "month" ? "30d" : "7d"),
        ]);
        if (cancelled) return;
        setBreakdown(b?.data);
        setTrends(t?.data);
        setSummary(s?.data as Record<string, unknown>);
        setError("");
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [period]);

  const breakdownArray = (() => {
    if (Array.isArray(breakdown)) return breakdown as Array<{ model: string; cost?: number }>;
    if (breakdown && typeof breakdown === "object") {
      const byModel = (breakdown as { by_model?: Record<string, number> }).by_model;
      if (byModel) return Object.entries(byModel).map(([model, cost]) => ({ model, cost }));
      return Object.entries(breakdown as Record<string, number>).map(([model, cost]) => ({ model, cost }));
    }
    return [];
  })();
  const trendArray = Array.isArray(trends) ? trends : trends && typeof trends === "object" && "points" in trends
    ? (trends as { points: Array<Record<string, unknown>> }).points
    : [];

  if (loading) {
    return (
      <DashboardLayout title="Analytics" subtitle="Loading…">
        <div className="animate-pulse space-y-6">
          <div className="h-64 bg-neutral-light-gray rounded-card" />
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout title="Analytics" subtitle="">
        <Card className="border-semantic-error bg-red-900/20">
          <p className="text-semantic-error">{error}</p>
        </Card>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="Analytics"
      subtitle="Deep insights into optimization metrics"
    >
      <div className="flex gap-2 mb-6">
        {["day", "week", "month"].map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className={`px-4 py-2 rounded-button text-sm font-medium transition ${
              period === p
                ? "bg-acron-primary_accent text-white"
                : "bg-neutral-light-gray text-neutral-dark-gray hover:bg-neutral-border hover:text-white"
            }`}
          >
            {p === "day" ? "24h" : p === "week" ? "7d" : "30d"}
          </button>
        ))}
      </div>

      <Card className="mb-8">
        <h3 className="text-lg font-bold text-white mb-4">Cost by Model</h3>
        <div className="h-64">
          {breakdownArray.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={breakdownArray} margin={{ top: 8, right: 8, left: 8, bottom: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="model" tick={{ fontSize: 12, fill: '#888' }} />
                <YAxis tick={{ fontSize: 12, fill: '#888' }} />
                <Tooltip contentStyle={{ backgroundColor: '#000', borderColor: '#333', color: '#fff' }} />
                <Legend />
                <Bar dataKey="cost" fill={ACRON_PRIMARY} name="Cost" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-neutral-dark-gray">
              No cost breakdown data yet
            </div>
          )}
        </div>
      </Card>

      <Card className="mb-8">
        <h3 className="text-lg font-bold text-white mb-4">Cost Trend</h3>
        <div className="h-64">
          {trendArray.length > 0 ? (
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendArray}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="interval" tick={{ fontSize: 12, fill: '#888' }} />
                <YAxis tick={{ fontSize: 12, fill: '#888' }} />
                <Tooltip contentStyle={{ backgroundColor: '#000', borderColor: '#333', color: '#fff' }} />
                <Line type="monotone" dataKey="value" stroke={ACRON_PRIMARY} strokeWidth={2} name="Cost" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex items-center justify-center text-neutral-dark-gray">
              No trend data yet
            </div>
          )}
        </div>
      </Card>

      <Card>
        <h3 className="text-lg font-bold text-white mb-4">Top Insights</h3>
        <ul className="space-y-2 text-neutral-dark-gray">
          <li>Total cost (period): ${typeof summary?.total_cost === "number" ? summary.total_cost.toFixed(2) : "—"}</li>
          <li>Total requests: {String(summary?.total_requests ?? "—")}</li>
          <li>Cache hit rate: {typeof summary?.cache_hit_rate === "number" ? (summary.cache_hit_rate * 100).toFixed(1) : "—"}%</li>
          <li>Cache cost saved: ${typeof summary?.cache_cost_saved === "number" ? summary.cache_cost_saved.toFixed(2) : "—"}</li>
        </ul>
      </Card>
    </DashboardLayout>
  );
}
