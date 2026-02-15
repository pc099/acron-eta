"use client";

import { Sidebar } from "./Sidebar";

export function DashboardLayout({
  children,
  title,
  subtitle,
}: {
  children: React.ReactNode;
  title: string;
  subtitle?: string;
}) {
  return (
    <div className="flex min-h-screen bg-neutral-light-gray">
      <Sidebar />
      <main className="flex-1 overflow-auto">
        <header className="bg-neutral-white border-b border-neutral-border px-8 py-6">
          <h1 className="text-2xl font-bold text-neutral-dark">{title}</h1>
          {subtitle && <p className="text-neutral-dark-gray mt-1">{subtitle}</p>}
        </header>
        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}
