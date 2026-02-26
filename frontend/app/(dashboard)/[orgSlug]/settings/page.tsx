"use client";

import { useQuery } from "@tanstack/react-query";
import { getOrg } from "@/lib/api";
import Link from "next/link";
import { Building2, Users } from "lucide-react";
import { formatNumber } from "@/lib/utils";

export default function SettingsPage({
  params,
}: {
  params: { orgSlug: string };
}) {
  const { data: org, isLoading } = useQuery({
    queryKey: ["org", params.orgSlug],
    queryFn: () => getOrg(params.orgSlug),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage your organisation settings and preferences
        </p>
      </div>

      {/* Navigation */}
      <div className="flex gap-4 border-b border-border">
        <div className="border-b-2 border-asahi px-4 py-2 text-sm font-medium text-asahi">
          General
        </div>
        <Link
          href={`/${params.orgSlug}/settings/team`}
          className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Team
        </Link>
        <Link
          href={`/${params.orgSlug}/settings/security`}
          className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Security
        </Link>
      </div>

      {isLoading ? (
        <div className="space-y-6">
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="animate-pulse space-y-4">
              <div className="h-5 w-40 rounded bg-muted" />
              <div className="h-4 w-64 rounded bg-muted" />
              <div className="h-4 w-48 rounded bg-muted" />
              <div className="h-4 w-56 rounded bg-muted" />
            </div>
          </div>
        </div>
      ) : !org ? (
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            Organisation not found.
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Org info */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-asahi/20">
                <Building2 className="h-5 w-5 text-asahi" />
              </div>
              <h2 className="text-lg font-semibold text-foreground">
                Organisation Details
              </h2>
            </div>

            <div className="space-y-4">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground">
                    Organisation Name
                  </label>
                  <p className="mt-1 text-sm font-medium text-foreground">
                    {org.name}
                  </p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground">
                    Slug
                  </label>
                  <p className="mt-1 font-mono text-sm text-foreground">
                    {org.slug}
                  </p>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground">
                    Plan
                  </label>
                  <span className="mt-1 inline-flex items-center rounded-full bg-asahi/20 px-2.5 py-0.5 text-xs font-medium text-asahi">
                    {org.plan}
                  </span>
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground">
                    Created
                  </label>
                  <p className="mt-1 text-sm text-foreground">
                    {new Date(org.created_at).toLocaleDateString()}
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Limits */}
          <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
            <h2 className="mb-6 text-lg font-semibold text-foreground">
              Plan Limits
            </h2>

            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <div>
                <label className="block text-xs font-medium text-muted-foreground">
                  Monthly Request Limit
                </label>
                <p className="mt-1 text-2xl font-bold text-foreground">
                  {formatNumber(org.monthly_request_limit)}
                </p>
                <p className="text-xs text-muted-foreground">requests per month</p>
              </div>
              <div>
                <label className="block text-xs font-medium text-muted-foreground">
                  Monthly Token Limit
                </label>
                <p className="mt-1 text-2xl font-bold text-foreground">
                  {formatNumber(org.monthly_token_limit)}
                </p>
                <p className="text-xs text-muted-foreground">tokens per month</p>
              </div>
            </div>
          </div>

          {/* Team shortcut */}
          <Link
            href={`/${params.orgSlug}/settings/team`}
            className="flex items-center gap-4 rounded-lg border border-border bg-card p-6 shadow-sm hover:bg-muted/50 transition-colors"
          >
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-asahi/20">
              <Users className="h-5 w-5 text-asahi" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground">
                Team Members
              </h3>
              <p className="text-xs text-muted-foreground">
                View and manage your team
              </p>
            </div>
          </Link>
        </div>
      )}
    </div>
  );
}
