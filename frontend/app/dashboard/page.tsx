"use client";

import { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { MetricCard } from "@/components/MetricCard";
import { Card } from "@/components/Card";
import {
  getMetrics,
  getCostSummary,
  getRecentInferences,
} from "@/lib/api";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

const ACRON_PRIMARY = "#D97B4A";
const ORANGE = "#D97B4A";

export default function DashboardPage() {
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [inferences, setInferences] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [m, s, r] = await Promise.all([
          getMetrics(),
          getCostSummary(),
          getRecentInferences(20),
        ]);
        if (cancelled) return;
        setMetrics(m);
        setSummary(s?.data as Record<string, unknown>);
        setInferences((r?.data?.inferences as Array<Record<string, unknown>>) || []);
        setError("");
      } catch (e) {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : "Failed to load";
          setError(msg);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const cacheHitRate = metrics
    ? Number(metrics.cache_hit_rate ?? 0) * 100
    : 0;
  const totalCost = metrics?.total_cost ?? summary?.total_cost ?? 0;
  const requests = metrics?.requests ?? summary?.total_requests ?? 0;
  const savings = metrics?.cache_cost_saved ?? summary?.cache_cost_saved ?? 0;
  const avgQuality = metrics?.avg_quality ?? summary?.avg_quality;
  const tier1 = Number(metrics?.tier1_hits ?? 0);
  const tier2 = Number(metrics?.tier2_hits ?? 0);
  const tier3 = Number(metrics?.tier3_hits ?? 0);
  const totalHits = tier1 + tier2 + tier3;

  const formatCost = (n: number) =>
    n >= 0.01 ? `$${n.toFixed(2)}` : (n > 0 ? `$${n.toFixed(4)}` : "$0.00");

  const pieData = [
    { name: "Tier 1", value: tier1, color: ORANGE },
    { name: "Tier 2", value: tier2, color: "#FFB84D" },
    { name: "Tier 3", value: tier3, color: "#E0E0E0" },
  ].filter((d) => d.value > 0);

  const lineData = inferences
    .slice(0, 10)
    .reverse()
    .map((i) => ({
      time: new Date(String(i.timestamp)).toLocaleTimeString(),
      cost: Number(i.cost ?? 0),
    }));

  if (loading) {
    return (
      <DashboardLayout title="Dashboard" subtitle="Loading…">
        <div className="animate-pulse space-y-6">
          <div className="grid grid-cols-4 gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-24 bg-neutral-border rounded-card" />
            ))}
          </div>
          <div className="h-64 bg-neutral-border rounded-card" />
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    const is401 = error.includes("401");
    return (
      <DashboardLayout title="Dashboard" subtitle="">
        <Card className="border-semantic-error bg-red-50">
          <p className="text-semantic-error">{error}</p>
          <p className="text-sm text-neutral-dark-gray mt-2">
            {is401
              ? "Your session may have expired or the API key is invalid. Log in again or update your key in Settings."
              : "Set your API base URL and API key in Settings, and ensure the backend is running."}
          </p>
          {is401 && (
            <p className="text-sm mt-2 flex gap-4">
              <a href="/login" className="text-acron-primary_accent hover:underline">Log in</a>
              <a href="/settings" className="text-acron-primary_accent hover:underline">Settings</a>
            </p>
          )}
        </Card>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="Dashboard"
      subtitle="Monitor your ACRON optimization metrics"
    >
      <div className="flex items-center gap-2 mb-2 text-sm text-neutral-dark-gray">
        <span className="w-2 h-2 rounded-full bg-emerald-500" aria-hidden />
        <span>ACRON Engine connected</span>
      </div>
      {typeof requests === "number" && requests === 0 && (
        <p className="text-sm text-neutral-dark-gray mb-4">
          No data yet. Run inference requests from the <a href="/inference" className="text-acron-primary_accent hover:underline">Inference</a> page to see metrics here.
        </p>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard
          value={totalHits > 0 ? Math.round(cacheHitRate) : "—"}
          label="Cost Savings (cache hit %)"
          unit={totalHits > 0 ? "%" : ""}
          highlight
        />
        <MetricCard
          value={typeof requests === "number" ? requests : Number(requests) || 0}
          label="Requests"
        />
        <MetricCard
          value={
            typeof totalCost === "number" ? formatCost(totalCost) : "—"
          }
          label="Total Cost"
          highlight
        />
        <MetricCard
          value={
            typeof avgQuality === "number" && !Number.isNaN(avgQuality)
              ? avgQuality.toFixed(1)
              : "—"
          }
          label="Quality"
          unit="/5"
        />
      </div>

      <div className="grid md:grid-cols-2 gap-6 mb-8">
        <Card>
          <h3 className="text-lg font-bold text-white mb-4">Cache Hit Rate</h3>
          <div className="h-64">
            {lineData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={lineData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                  <XAxis dataKey="time" tick={{ fontSize: 12, fill: '#888' }} />
                  <YAxis tick={{ fontSize: 12, fill: '#888' }} />
                  <Tooltip contentStyle={{ backgroundColor: '#000', borderColor: '#333' }} />
                  <Line type="monotone" dataKey="cost" stroke={ACRON_PRIMARY} strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-neutral-dark-gray">
                {cacheHitRate > 0 ? `${cacheHitRate.toFixed(1)}% current` : "No data yet"}
              </div>
            )}
          </div>
        </Card>
        <Card>
          <h3 className="text-lg font-bold text-neutral-dark mb-4">Cost by Tier</h3>
          <div className="h-64">
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={50}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                    nameKey="name"
                    label={({ name, value }) => `${name}: ${value}`}
                  >
                    {pieData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Pie>
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-neutral-dark-gray">
                No cache data yet
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card>
        <h3 className="text-lg font-bold text-neutral-dark mb-4">Recent Inferences</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-border text-left text-neutral-dark-gray">
                <th className="py-2 pr-4">Time</th>
                <th className="py-2 pr-4">Model</th>
                <th className="py-2 pr-4">Cost</th>
                <th className="py-2 pr-4">Cache</th>
              </tr>
            </thead>
            <tbody>
              {inferences.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-8 text-center text-neutral-dark-gray">
                    No recent inferences. Run one from the Inference page.
                  </td>
                </tr>
              ) : (
                inferences.map((inf, i) => (
                  <tr key={String(inf.request_id || i)} className="border-b border-neutral-border">
                    <td className="py-2 pr-4">
                      {inf.timestamp
                        ? new Date(String(inf.timestamp)).toLocaleTimeString()
                        : "—"}
                    </td>
                    <td className="py-2 pr-4">{String(inf.model_used || "—")}</td>
                    <td className="py-2 pr-4">
                      $
                      {typeof inf.cost === "number"
                        ? inf.cost.toFixed(4)
                        : String(inf.cost ?? "—")}
                    </td>
                    <td className="py-2 pr-4">
                      {inf.cache_hit ? "✓" : "✗"}
                      {inf.cache_hit && inf.cache_tier ? ` T${inf.cache_tier}` : ""}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </DashboardLayout>
  );
}
