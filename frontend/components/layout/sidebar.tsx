"use client";

import Link from "next/link";
import {
  BarChart2,
  CreditCard,
  Database,
  Key,
  LayoutDashboard,
  Settings,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { icon: LayoutDashboard, label: "Dashboard", path: "/dashboard" },
  { icon: Zap, label: "Gateway", path: "/gateway" },
  { icon: Database, label: "Cache", path: "/cache" },
  { icon: BarChart2, label: "Analytics", path: "/analytics" },
  { icon: Key, label: "API Keys", path: "/keys" },
];

const bottomItems = [
  { icon: Settings, label: "Settings", path: "/settings" },
];

interface SidebarProps {
  orgSlug: string;
  currentPath: string;
}

export function Sidebar({ orgSlug, currentPath }: SidebarProps) {
  const isActive = (path: string) =>
    currentPath.includes(`/${orgSlug}${path}`);

  return (
    <aside className="hidden w-64 flex-col border-r border-border bg-sidebar md:flex">
      {/* Logo */}
      <div className="flex h-14 items-center gap-2 border-b border-border px-6">
        <div className="h-7 w-7 rounded-md bg-asahi flex items-center justify-center">
          <span className="text-sm font-bold text-white">A</span>
        </div>
        <span className="text-lg font-bold text-foreground">ASAHI</span>
      </div>

      {/* Nav items */}
      <nav className="flex-1 space-y-1 px-3 py-4">
        {navItems.map((item) => {
          const href = `/${orgSlug}${item.path}`;
          const active = isActive(item.path);
          return (
            <Link
              key={item.path}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150",
                active
                  ? "border-l-2 border-asahi bg-asahi/10 text-asahi"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Bottom nav */}
      <div className="border-t border-border px-3 py-4">
        {bottomItems.map((item) => {
          const href = `/${orgSlug}${item.path}`;
          const active = isActive(item.path);
          return (
            <Link
              key={item.path}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150",
                active
                  ? "border-l-2 border-asahi bg-asahi/10 text-asahi"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
              )}
            >
              <item.icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </div>

      {/* Org slug footer */}
      <div className="border-t border-border px-6 py-3">
        <p className="truncate text-xs text-muted-foreground">{orgSlug}</p>
      </div>
    </aside>
  );
}
