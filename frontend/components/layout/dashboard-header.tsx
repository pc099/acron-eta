"use client";

import { UserButton } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { Menu } from "lucide-react";
import { getAnalyticsOverview } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

interface DashboardHeaderProps {
  orgSlug: string;
  onMenuToggle?: () => void;
}

export function DashboardHeader({
  orgSlug,
  onMenuToggle,
}: DashboardHeaderProps) {
  const { data: overview } = useQuery({
    queryKey: ["overview", orgSlug],
    queryFn: () => getAnalyticsOverview("30d"),
    refetchInterval: 30_000,
  });

  return (
    <header className="flex h-14 items-center justify-between border-b border-border bg-background px-6">
      <div className="flex items-center gap-4">
        {onMenuToggle && (
          <button
            type="button"
            aria-label="Open sidebar"
            className="flex h-8 w-8 items-center justify-center rounded-md border border-border bg-background text-muted-foreground hover:bg-muted md:hidden"
            onClick={onMenuToggle}
          >
            <Menu className="h-4 w-4" />
          </button>
        )}
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

