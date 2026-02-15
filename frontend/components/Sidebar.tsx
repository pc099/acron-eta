"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

const navItems = [
  { icon: "📊", label: "Dashboard", path: "/dashboard" },
  { icon: "🚀", label: "Get Started", path: "/getting-started" },
  { icon: "⚡", label: "Inference", path: "/inference" },
  { icon: "💾", label: "Cache", path: "/cache" },
  { icon: "📈", label: "Analytics", path: "/analytics" },
  { icon: "👤", label: "Profile", path: "/profile" },
  { icon: "⚙️", label: "Settings", path: "/settings" },
];

const API_KEY_STORAGE = "acron_api_key";

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    if (typeof window !== "undefined") {
      localStorage.removeItem(API_KEY_STORAGE);
      router.push("/login");
    }
  }

  return (
    <aside className="w-64 min-w-[256px] bg-neutral-dark border-r border-neutral-border h-screen sticky top-0 flex flex-col">
      <div className="p-6 border-b border-neutral-border">
        <Link href="/dashboard" className="flex items-center gap-2">
          <img src="/logo.svg" alt="ACRON" className="w-8 h-8 rounded object-contain" />
          <span className="font-bold text-white">ACRON</span>
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
                  ? "bg-acron-primary_accent/20 text-acron-primary_accent"
                  : "text-neutral-dark-gray hover:bg-acron-primary_accent/10 hover:text-acron-primary_accent"
              }`}
            >
              <span>{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
      </nav>
      <div className="p-4 border-t border-neutral-border">
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-3 rounded-card w-full text-left text-neutral-dark-gray hover:bg-red-500/10 hover:text-semantic-error transition"
        >
          <span>🚪</span>
          <span className="font-medium">Log out</span>
        </button>
      </div>
    </aside>
  );
}
