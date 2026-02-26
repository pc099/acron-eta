"use client";

import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/sidebar";
import { DashboardHeader } from "@/components/layout/dashboard-header";

export default function OrgLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: { orgSlug: string };
}) {
  const pathname = usePathname();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar orgSlug={params.orgSlug} currentPath={pathname} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <DashboardHeader orgSlug={params.orgSlug} />
        <main className="flex-1 overflow-y-auto p-6">{children}</main>
      </div>
    </div>
  );
}
