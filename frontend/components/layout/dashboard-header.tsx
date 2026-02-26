"use client";

import { UserButton } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { getAnalyticsOverview } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

interface DashboardHeaderProps {
  orgSlug: string;
}

export function DashboardHeader({ orgSlug }: DashboardHeaderProps) {
  const { data: overview } = useQuery({
    queryKey: ["overview", orgSlug],
    queryFn: () => getAnalyticsOverview("30d"),
    refetchInterval: 30_000,
  });

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex items-center gap-4">
        <h2 className="text-sm font-medium text-muted-foreground">
          {orgSlug}
        </h2>
        {overview && overview.total_savings_usd > 0 && (
          <span className="text-sm font-semibold text-asahi">
            {formatCurrency(overview.total_savings_usd)} saved this month
          </span>
        )}
      </div>
      <div className="flex items-center gap-4">
        <UserButton afterSignOutUrl="/sign-in" />
      </div>
    </header>
  );
}
