"use client";

import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import type { ModelBreakdown } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

const COLORS = ["#FF6B35", "#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#00BCD4"];

interface ModelDistributionChartProps {
  data: ModelBreakdown[];
}

export function ModelDistributionChart({ data }: ModelDistributionChartProps) {
  return (
    <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
      <h3 className="mb-4 text-sm font-semibold text-foreground">
        Cost by Model
      </h3>
      {data.length === 0 ? (
        <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
          No model data yet.
        </div>
      ) : (
        <div className="flex items-center gap-6">
          <ResponsiveContainer width="50%" height={240}>
            <PieChart>
              <Pie
                data={data}
                dataKey="total_cost"
                nameKey="model"
                cx="50%"
                cy="50%"
                innerRadius={50}
                outerRadius={90}
                paddingAngle={2}
              >
                {data.map((_, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={COLORS[index % COLORS.length]}
                  />
                ))}
              </Pie>
              <Tooltip
                contentStyle={{
                  backgroundColor: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: "8px",
                }}
                formatter={(value: number) => [formatCurrency(value), "Cost"]}
              />
            </PieChart>
          </ResponsiveContainer>
          <div className="flex-1 space-y-2">
            {data.map((item, index) => (
              <div key={item.model} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <div
                    className="h-3 w-3 rounded-full"
                    style={{ backgroundColor: COLORS[index % COLORS.length] }}
                  />
                  <span className="text-foreground">{item.model}</span>
                </div>
                <span className="text-muted-foreground">
                  {item.requests} req
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
