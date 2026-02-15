"use client";

import { useEffect, useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { MetricCard } from "@/components/MetricCard";
import { Card } from "@/components/Card";
import { getMetrics, getRecentInferences } from "@/lib/api";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";

const ACRON_PRIMARY = "#FF6B35";

export default function CachePage() {
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [inferences, setInferences] = useState<Array<Record<string, unknown>>>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [m, r] = await Promise.all([
          getMetrics(),
          getRecentInferences(30),
        ]);
        if (cancelled) return;
        setMetrics(m);
        setInferences((r?.data?.inferences as Array<Record<string, unknown>>) || []);
        setError("");
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const tier1Hits = Number(metrics?.tier1_hits ?? 0);
  const tier2Hits = Number(metrics?.tier2_hits ?? 0);
  const tier3Hits = Number(metrics?.tier3_hits ?? 0);
  const cacheSize = Number(metrics?.cache_size ?? 0);
  const hitRate = (Number(metrics?.cache_hit_rate ?? 0) * 100).toFixed(1);
  const totalHits = tier1Hits + tier2Hits + tier3Hits;
  const barData = [
    { tier: "Tier 1", hits: tier1Hits, pct: totalHits ? Math.round((tier1Hits / totalHits) * 100) : 0 },
    { tier: "Tier 2", hits: tier2Hits, pct: totalHits ? Math.round((tier2Hits / totalHits) * 100) : 0 },
    { tier: "Tier 3", hits: tier3Hits, pct: totalHits ? Math.round((tier3Hits / totalHits) * 100) : 0 },
  ];

  if (loading) {
    return (
      <DashboardLayout title="Cache Management" subtitle="Loading…">
        <div className="animate-pulse space-y-6">
          <div className="grid grid-cols-3 gap-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-neutral-light-gray rounded-card" />
            ))}
          </div>
        </div>
      </DashboardLayout>
    );
  }

  if (error) {
    return (
      <DashboardLayout title="Cache Management" subtitle="">
        <Card className="border-semantic-error bg-red-900/20">
          <p className="text-semantic-error">{error}</p>
        </Card>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout
      title="Cache Management"
      subtitle="Monitor and manage caching strategy"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
        <MetricCard value={cacheSize} label="Total Cached (entries)" />
        <MetricCard value={tier1Hits} label="Tier 1 Hits" unit={` (${totalHits ? Math.round((tier1Hits / totalHits) * 100) : 0}%)`} />
        <MetricCard value={tier2Hits} label="Tier 2 Hits" unit={` (${totalHits ? Math.round((tier2Hits / totalHits) * 100) : 0}%)`} />
        <MetricCard value={tier3Hits} label="Tier 3 Hits" unit={` (${totalHits ? Math.round((tier3Hits / totalHits) * 100) : 0}%)`} />
        <MetricCard value={hitRate} label="Hit Rate (All Tiers)" unit="%" highlight />
        <MetricCard value="—" label="Storage Used" unit="" />
      </div>

      <Card className="mb-8">
        <h3 className="text-lg font-bold text-white mb-4">Cache Hit Rate Over Time</h3>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={barData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#333" />
              <XAxis dataKey="tier" tick={{ fill: '#888' }} />
              <YAxis tick={{ fill: '#888' }} />
              <Tooltip contentStyle={{ backgroundColor: '#000', borderColor: '#333', color: '#fff' }} />
              <Legend />
              <Bar dataKey="hits" fill={ACRON_PRIMARY} name="Hits" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <Card>
        <h3 className="text-lg font-bold text-white mb-4">Recent Cache Activity</h3>
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
              {inferences.slice(0, 10).map((inf, i) => (
                <tr key={i} className="border-b border-neutral-border text-white">
                  <td className="py-2 pr-4">
                    {inf.timestamp
                      ? new Date(String(inf.timestamp)).toLocaleTimeString()
                      : "—"}
                  </td>
                  <td className="py-2 pr-4">{String(inf.model_used || "—")}</td>
                  <td className="py-2 pr-4">${typeof inf.cost === "number" ? inf.cost.toFixed(4) : "—"}</td>
                  <td className="py-2 pr-4">{inf.cache_hit ? "✓" : "✗"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm text-neutral-dark-gray mt-4">
          Cache controls (clear/export) are available via API. Use Settings to configure TTL and thresholds.
        </p>
      </Card>
    </DashboardLayout>
  );
}
