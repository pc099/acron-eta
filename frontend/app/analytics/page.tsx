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

const ACRON_PRIMARY = "#D97B4A";

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
        const periodParam = period === "day" ? "24h" : period === "month" ? "30d" : "7d";
        const [b, t, s] = await Promise.all([
          getCostBreakdown(period, "model"),
          getTrends("cost", period, 30),
          getCostSummary(periodParam),
        ]);
        if (cancelled) return;
        const bData = typeof b === "object" && b !== null && "data" in b ? (b as { data: unknown }).data : b;
        const tData = typeof t === "object" && t !== null && "data" in t ? (t as { data: unknown }).data : t;
        const sData = typeof s === "object" && s !== null && "data" in s ? (s as { data: unknown }).data : s;
        setBreakdown(bData);
        setTrends(tData);
        setSummary(sData as Record<string, unknown> | null);
        setError("");
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load");
          setBreakdown(null);
          setTrends(null);
          setSummary(null);
        }
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
      if (byModel) return Object.entries(byModel).map(([model, cost]) => ({ model, cost: Number(cost) }));
      const entries = Object.entries(breakdown as Record<string, unknown>).filter(([, v]) => typeof v === "number");
      return entries.map(([model, cost]) => ({ model, cost: cost as number }));
    }
    return [];
  })();
  const trendArray = (() => {
    if (Array.isArray(trends)) return trends as Array<Record<string, unknown>>;
    if (trends && typeof trends === "object" && "points" in trends)
      return (trends as { points: Array<Record<string, unknown>> }).points;
    if (trends && typeof trends === "object" && "intervals" in trends)
      return (trends as { intervals: Array<Record<string, unknown>> }).intervals as Array<Record<string, unknown>>;
    return [];
  })();

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
                <XAxis dataKey="model" tick={{ fontSize: 12, fill: "#888" }} />
                <YAxis tick={{ fontSize: 12, fill: "#888" }} />
                <Tooltip contentStyle={{ backgroundColor: "#1a1a1a", borderColor: "#374151", color: "#fff" }} />
                <Legend />
                <Bar dataKey="cost" fill={ACRON_PRIMARY} name="Cost" />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-neutral-dark-gray gap-2">
              <p>No cost breakdown data yet.</p>
              <p className="text-sm">Run inference requests to see cost by model here.</p>
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
                <XAxis dataKey={trendArray[0] && "timestamp" in trendArray[0] ? "timestamp" : "interval"} tick={{ fontSize: 12, fill: "#888" }} />
                <YAxis tick={{ fontSize: 12, fill: "#888" }} />
                <Tooltip contentStyle={{ backgroundColor: "#1a1a1a", borderColor: "#374151", color: "#fff" }} />
                <Line type="monotone" dataKey="value" stroke={ACRON_PRIMARY} strokeWidth={2} name="Cost" />
              </LineChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-neutral-dark-gray gap-2">
              <p>No trend data yet.</p>
              <p className="text-sm">Use inference over time to see cost trends.</p>
            </div>
          )}
        </div>
      </Card>

      <Card>
        <h3 className="text-lg font-bold text-white mb-4">Summary</h3>
        <ul className="space-y-3 text-neutral-dark-gray">
          <li className="flex justify-between">
            <span>Total cost (period)</span>
            <span className="text-white font-medium">
              ${typeof summary?.total_cost === "number" ? summary.total_cost.toFixed(2) : "0.00"}
            </span>
          </li>
          <li className="flex justify-between">
            <span>Total requests</span>
            <span className="text-white font-medium">{String(summary?.total_requests ?? 0)}</span>
          </li>
          <li className="flex justify-between">
            <span>Cache hit rate</span>
            <span className="text-white font-medium">
              {typeof summary?.cache_hit_rate === "number" ? (summary.cache_hit_rate * 100).toFixed(1) : "0"}%
            </span>
          </li>
          <li className="flex justify-between">
            <span>Cache cost saved</span>
            <span className="text-white font-medium">
              ${typeof summary?.cache_cost_saved === "number" ? summary.cache_cost_saved.toFixed(2) : "0.00"}
            </span>
          </li>
        </ul>
      </Card>
    </DashboardLayout>
  );
}
