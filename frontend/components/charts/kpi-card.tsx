"use client";

import type { LucideIcon } from "lucide-react";
import { cn, formatCurrency, formatNumber, formatPercent } from "@/lib/utils";
import { TrendingDown, TrendingUp } from "lucide-react";

interface KpiCardProps {
  title: string;
  value: number;
  format: "currency" | "percentage" | "number";
  suffix?: string;
  delta?: number;
  deltaLabel?: string;
  icon?: LucideIcon;
  loading?: boolean;
  highlight?: boolean;
}

export function KpiCard({
  title,
  value,
  format,
  suffix,
  delta,
  deltaLabel,
  icon: Icon,
  loading,
  highlight,
}: KpiCardProps) {
  const formattedValue = (() => {
    switch (format) {
      case "currency":
        return formatCurrency(value);
      case "percentage":
        return formatPercent(value);
      case "number":
        return formatNumber(value) + (suffix ? ` ${suffix}` : "");
    }
  })();

  if (loading) {
    return (
      <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-24 rounded bg-muted" />
          <div className="h-8 w-32 rounded bg-muted" />
          <div className="h-3 w-20 rounded bg-muted" />
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-muted-foreground">{title}</p>
        {Icon && (
          <Icon
            className={cn(
              "h-4 w-4",
              highlight ? "text-asahi" : "text-muted-foreground"
            )}
          />
        )}
      </div>
      <p
        className={cn(
          "mt-2 text-2xl font-bold",
          highlight ? "text-asahi" : "text-foreground"
        )}
      >
        {formattedValue}
      </p>
      {delta !== undefined && (
        <div className="mt-1 flex items-center gap-1">
          {delta >= 0 ? (
            <TrendingUp className="h-3 w-3 text-green-500" />
          ) : (
            <TrendingDown className="h-3 w-3 text-red-500" />
          )}
          <span
            className={cn(
              "text-xs font-medium",
              delta >= 0 ? "text-green-500" : "text-red-500"
            )}
          >
            {delta >= 0 ? "+" : ""}
            {delta.toFixed(1)}%
          </span>
          {deltaLabel && (
            <span className="text-xs text-muted-foreground">{deltaLabel}</span>
          )}
        </div>
      )}
    </div>
  );
}
