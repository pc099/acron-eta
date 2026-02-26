"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SavingsDataPoint } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

interface SavingsChartProps {
  data: SavingsDataPoint[];
}

export function SavingsChart({ data }: SavingsChartProps) {
  const chartData = data.map((d) => ({
    ...d,
    date: new Date(d.timestamp).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold text-foreground">
        Savings Over Time
      </h3>
      {chartData.length === 0 ? (
        <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
          No data yet. Make some requests to see savings.
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <AreaChart data={chartData}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="hsl(var(--border))"
            />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
            />
            <YAxis
              tick={{ fontSize: 12, fill: "hsl(var(--muted-foreground))" }}
              tickFormatter={(v: number) => `$${v.toFixed(2)}`}
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "hsl(var(--card))",
                border: "1px solid hsl(var(--border))",
                borderRadius: "8px",
              }}
              labelStyle={{ color: "hsl(var(--foreground))" }}
              formatter={(value: number, name: string) => [
                formatCurrency(value),
                name === "cost_without_asahi"
                  ? "Without ASAHI"
                  : name === "cost_with_asahi"
                    ? "With ASAHI"
                    : "Savings",
              ]}
            />
            <Area
              type="monotone"
              dataKey="cost_without_asahi"
              stroke="hsl(var(--muted-foreground))"
              strokeDasharray="5 5"
              fill="transparent"
              name="Without ASAHI"
            />
            <Area
              type="monotone"
              dataKey="cost_with_asahi"
              stroke="#FF6B35"
              fill="#FF6B35"
              fillOpacity={0.1}
              name="With ASAHI"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
