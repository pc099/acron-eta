"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { icon: "📊", label: "Dashboard", path: "/dashboard" },
  { icon: "⚡", label: "Inference", path: "/inference" },
  { icon: "💾", label: "Cache", path: "/cache" },
  { icon: "📈", label: "Analytics", path: "/analytics" },
  { icon: "⚙️", label: "Settings", path: "/settings" },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-64 min-w-[256px] bg-neutral-white border-r border-neutral-border h-screen sticky top-0 flex flex-col">
      <div className="p-6 border-b border-neutral-border">
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded bg-asahi-orange flex items-center justify-center">
            <span className="text-white font-bold">A</span>
          </div>
          <span className="font-bold text-neutral-dark">ASAHI</span>
        </Link>
      </div>
      <nav className="p-4 flex-1">
        {navItems.map((item) => {
          const isActive = pathname === item.path;
          return (
            <Link
              key={item.path}
              href={item.path}
              className={`flex items-center gap-3 px-4 py-3 rounded-card mb-2 transition ${
                isActive
                  ? "bg-asahi-orange-very-light text-asahi-orange"
                  : "text-neutral-dark-gray hover:bg-asahi-orange-very-light hover:text-asahi-orange"
              }`}
            >
              <span>{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
