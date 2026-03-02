"use client";

import { useEffect, useRef } from "react";
import { UserButton } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { Menu } from "lucide-react";
import { getAnalyticsOverview } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { fireConfetti } from "@/lib/confetti";
import { toast } from "sonner";

interface DashboardHeaderProps {
  orgSlug: string;
  onMenuToggle?: () => void;
}

export function DashboardHeader({
  orgSlug,
  onMenuToggle,
}: DashboardHeaderProps) {
  const prevRequests = useRef<number | null>(null);
  const confettiFired = useRef(false);

  const { data: overview } = useQuery({
    queryKey: ["overview", orgSlug],
    queryFn: () => getAnalyticsOverview("30d"),
    refetchInterval: 30_000,
  });

  // Fire confetti when request count transitions from 0 to >0
  useEffect(() => {
    if (!overview || confettiFired.current) return;
    const total = overview.total_requests;
    if (prevRequests.current !== null && prevRequests.current === 0 && total > 0) {
      confettiFired.current = true;
      fireConfetti();
      toast.success("First request detected! Your savings are rolling in.");
    }
    prevRequests.current = total;
  }, [overview]);

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
        <kbd className="hidden items-center gap-0.5 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground sm:flex">
          <span className="text-xs">&#8984;</span>K
        </kbd>
        <UserButton afterSignOutUrl="/sign-in" />
      </div>
    </header>
  );
}

