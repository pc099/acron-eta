"use client";

import Link from "next/link";
import type { RequestLogEntry } from "@/lib/api";
import { cn, formatCurrency } from "@/lib/utils";

interface RecentRequestsTableProps {
  data: RequestLogEntry[];
  orgSlug: string;
}

const tierColors: Record<string, string> = {
  exact: "bg-green-500/20 text-green-400",
  semantic: "bg-blue-500/20 text-blue-400",
  intermediate: "bg-purple-500/20 text-purple-400",
};

export function RecentRequestsTable({
  data,
  orgSlug,
}: RecentRequestsTableProps) {
  return (
    <div className="rounded-lg border border-border bg-card shadow-sm">
      <div className="flex items-center justify-between border-b border-border p-4">
        <h3 className="text-sm font-semibold text-foreground">
          Recent Requests
        </h3>
        <Link
          href={`/${orgSlug}/gateway`}
          className="text-xs font-medium text-asahi hover:underline"
        >
          View all requests →
        </Link>
      </div>
      {data.length === 0 ? (
        <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
          No requests yet. Send your first request to see it here.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-3">Time</th>
                <th className="px-4 py-3">Model</th>
                <th className="px-4 py-3">Tokens</th>
                <th className="px-4 py-3">Without ASAHI</th>
                <th className="px-4 py-3">With ASAHI</th>
                <th className="px-4 py-3">Cache</th>
                <th className="px-4 py-3">Savings</th>
                <th className="px-4 py-3">Latency</th>
              </tr>
            </thead>
            <tbody>
              {data.map((row) => (
                <tr
                  key={row.id}
                  className="border-b border-border last:border-0 hover:bg-muted/50 transition-colors"
                >
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(row.created_at).toLocaleTimeString()}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-foreground">
                    {row.model_used}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {row.input_tokens + row.output_tokens}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {formatCurrency(row.cost_without_asahi)}
                  </td>
                  <td className="px-4 py-3 text-foreground">
                    {formatCurrency(row.cost_with_asahi)}
                  </td>
                  <td className="px-4 py-3">
                    {row.cache_hit ? (
                      <span
                        className={cn(
                          "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
                          tierColors[row.cache_tier || ""] ||
                            "bg-muted text-muted-foreground"
                        )}
                      >
                        {row.cache_tier || "hit"}
                      </span>
                    ) : (
                      <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                        miss
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {row.savings_pct !== null && row.savings_pct > 0 ? (
                      <span className="text-xs font-medium text-green-400">
                        {row.savings_pct.toFixed(0)}% off
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">-</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {row.latency_ms ? `${row.latency_ms}ms` : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
