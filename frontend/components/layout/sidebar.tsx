"use client";

import Link from "next/link";
import {
  Activity,
  BarChart2,
  BookOpen,
  Bot,
  CreditCard,
  Database,
  GitBranch,
  Key,
  LayoutDashboard,
  Server,
  Settings,
  Shield,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: Zap, label: "Gateway", path: "/gateway" },
  { icon: Bot, label: "Agents", path: "/agents" },
  { icon: Database, label: "Cache", path: "/cache" },
  { icon: Activity, label: "Traces", path: "/traces" },
  { icon: BarChart2, label: "Analytics", path: "/analytics" },
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
  const isActive = (path: string) => currentPath.includes(`/${orgSlug}${path}`);

  return (
    <>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
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

export function Sidebar({
  orgSlug,
  currentPath,
  isOpen = false,
  onClose,
}: SidebarProps) {
  return (
    <>
      <aside className="hidden w-64 flex-col border-r border-border bg-sidebar md:flex">
        <div className="flex h-14 items-center gap-2 border-b border-border px-6">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-asahio">
            <span className="text-sm font-bold text-white">A</span>
          </div>
          <span className="text-lg font-bold text-foreground">ASAHIO</span>
        </div>
        <SidebarNav orgSlug={orgSlug} currentPath={currentPath} />
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
            <div className="flex h-14 items-center gap-2 border-b border-border px-6">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-asahio">
                <span className="text-sm font-bold text-white">A</span>
              </div>
              <span className="text-lg font-bold text-foreground">ASAHIO</span>
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
