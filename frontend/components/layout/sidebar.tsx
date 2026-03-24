"use client";

import Image from "next/image";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  BarChart2,
  BookOpen,
  Bot,
  Brain,
  CreditCard,
  Database,
  GitBranch,
  Key,
  LayoutDashboard,
  Radar,
  Server,
  Settings,
  Shield,
  ShieldAlert,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { getOrgUsage } from "@/lib/api";

interface NavItem {
  icon: typeof LayoutDashboard;
  label: string;
  path: string;
  absolute?: boolean;
}

const navItems: NavItem[] = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: Zap, label: "Gateway", path: "/gateway" },
  { icon: Bot, label: "Agents", path: "/agents" },
  { icon: Database, label: "Cache", path: "/cache" },
  { icon: Activity, label: "Traces", path: "/traces" },
  { icon: BarChart2, label: "Analytics", path: "/analytics" },
  { icon: Brain, label: "ABA", path: "/aba" },
  { icon: Radar, label: "Fleet", path: "/fleet" },
  { icon: ShieldAlert, label: "Interventions", path: "/interventions" },
  { icon: GitBranch, label: "Routing", path: "/routing" },
  { icon: Server, label: "Models", path: "/models" },
  { icon: CreditCard, label: "Billing", path: "/billing" },
  { icon: Key, label: "API Keys", path: "/keys" },
  { icon: Shield, label: "Governance", path: "/governance" },
  { icon: BookOpen, label: "Docs", path: "/docs" },
];

const bottomItems = [
  { icon: Settings, label: "Settings", path: "/settings" },
];

interface SidebarProps {
  orgSlug: string;
  currentPath: string;
  isOpen?: boolean;
  onClose?: () => void;
}

interface NavProps {
  orgSlug: string;
  currentPath: string;
  onItemClick?: () => void;
}

function SidebarNav({ orgSlug, currentPath, onItemClick }: NavProps) {
  const isActive = (path: string, absolute?: boolean) =>
    absolute ? currentPath === path : currentPath.includes(`/${orgSlug}${path}`);

  return (
    <>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const href = item.absolute ? item.path : `/${orgSlug}${item.path}`;
          const active = isActive(item.path, item.absolute);
          const classes = cn(
            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150",
            active
              ? "border-l-2 border-asahio bg-asahio/10 text-asahio"
              : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
          );

          // Use <a> for absolute links to force full page navigation
          // (Link does client-side routing which gets caught by [orgSlug])
          if (item.absolute) {
            return (
              <a key={item.path} href={href} onClick={onItemClick} className={classes}>
                <item.icon className="h-4 w-4" />
                {item.label}
              </a>
            );
          }

          return (
            <Link key={item.path} href={href} onClick={onItemClick} className={classes}>
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border px-3 py-4">
        {bottomItems.map((item) => {
          const href = `/${orgSlug}${item.path}`;
          const active = isActive(item.path);
          return (
            <Link
              key={item.path}
              href={href}
              onClick={onItemClick}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150",
                active
                  ? "border-l-2 border-asahio bg-asahio/10 text-asahio"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </div>
    </>
  );
}

function UsageBars({ orgSlug }: { orgSlug: string }) {
  const { data: usage } = useQuery({
    queryKey: ["usage", orgSlug, "sidebar"],
    queryFn: () => getOrgUsage(orgSlug),
    refetchInterval: 60_000,
  });

  if (!usage) return null;

  const barColor = (pct: number) =>
    pct >= 95 ? "bg-red-500" : pct >= 80 ? "bg-orange-500" : pct >= 60 ? "bg-yellow-500" : "bg-asahio";

  return (
    <div className="space-y-2 px-6 py-3 border-t border-border">
      <div>
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>Requests</span>
          <span>{usage.requests_pct.toFixed(0)}%</span>
        </div>
        <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full transition-all", barColor(usage.requests_pct))}
            style={{ width: `${Math.min(100, usage.requests_pct)}%` }}
          />
        </div>
      </div>
      <div>
        <div className="flex justify-between text-[10px] text-muted-foreground">
          <span>Tokens</span>
          <span>{usage.tokens_pct.toFixed(0)}%</span>
        </div>
        <div className="mt-0.5 h-1.5 w-full overflow-hidden rounded-full bg-muted">
          <div
            className={cn("h-full rounded-full transition-all", barColor(usage.tokens_pct))}
            style={{ width: `${Math.min(100, usage.tokens_pct)}%` }}
          />
        </div>
      </div>
    </div>
  );
}

export function Sidebar({
  orgSlug,
  currentPath,
  isOpen = false,
  onClose,
}: SidebarProps) {
  return (
    <>
      <aside className="hidden w-64 flex-col border-r border-border bg-sidebar md:flex">
        <div className="flex h-16 items-center gap-3 border-b border-border px-6">
          <Image src="/asashio_logo-NB.png" alt="ASAHIO" width={40} height={40} className="rounded-md" />
          <span className="text-xl font-bold text-foreground">ASAHIO</span>
        </div>
        <SidebarNav orgSlug={orgSlug} currentPath={currentPath} />
        <UsageBars orgSlug={orgSlug} />
        <div className="border-t border-border px-6 py-3">
          <p className="truncate text-xs text-muted-foreground">{orgSlug}</p>
        </div>
      </aside>

      {isOpen && (
        <div className="fixed inset-0 z-40 flex md:hidden">
          <button
            type="button"
            aria-label="Close sidebar"
            className="fixed inset-0 bg-black/40"
            onClick={onClose}
          />
          <aside className="relative z-50 flex h-full w-64 flex-col border-r border-border bg-sidebar shadow-lg">
            <div className="flex h-16 items-center gap-3 border-b border-border px-6">
              <Image src="/asashio_logo-NB.png" alt="ASAHIO" width={40} height={40} className="rounded-md" />
              <span className="text-xl font-bold text-foreground">ASAHIO</span>
            </div>
            <SidebarNav
              orgSlug={orgSlug}
              currentPath={currentPath}
              onItemClick={onClose}
            />
            <div className="border-t border-border px-6 py-3">
              <p className="truncate text-xs text-muted-foreground">{orgSlug}</p>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}
