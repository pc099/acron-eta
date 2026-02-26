"use client";

import { useQuery } from "@tanstack/react-query";
import { getAuditLog } from "@/lib/api";
import Link from "next/link";
import { Shield } from "lucide-react";
import { useState } from "react";

export default function SecurityPage({
  params,
}: {
  params: { orgSlug: string };
}) {
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["audit-log", page],
    queryFn: () => getAuditLog({ page, limit: 25 }),
  });

  const entries = data?.data ?? [];
  const pagination = data?.pagination;

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Security</h1>
        <p className="text-sm text-muted-foreground">
          Audit log and security events
        </p>
      </div>

      {/* Navigation */}
      <div className="flex gap-4 border-b border-border">
        <Link
          href={`/${params.orgSlug}/settings`}
          className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          General
        </Link>
        <Link
          href={`/${params.orgSlug}/settings/team`}
          className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Team
        </Link>
        <div className="border-b-2 border-asahi px-4 py-2 text-sm font-medium text-asahi">
          Security
        </div>
      </div>

      {/* Audit log table */}
      <div className="rounded-lg border border-border bg-card shadow-sm">
        <div className="flex items-center gap-3 border-b border-border px-4 py-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-asahi/20">
            <Shield className="h-4 w-4 text-asahi" />
          </div>
          <h2 className="text-sm font-semibold text-foreground">Audit Log</h2>
        </div>

        {isLoading ? (
          <div className="animate-pulse space-y-4 p-6">
            {[1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="h-10 rounded bg-muted" />
            ))}
          </div>
        ) : entries.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3">
            <Shield className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No audit log entries yet.
            </p>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-3">Time</th>
                  <th className="px-4 py-3">Actor</th>
                  <th className="px-4 py-3">Action</th>
                  <th className="px-4 py-3">Resource</th>
                  <th className="px-4 py-3">IP</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-border last:border-0 hover:bg-muted/50 transition-colors"
                  >
                    <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                      {new Date(entry.timestamp).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 font-medium text-foreground">
                      {entry.actor}
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                        {entry.action}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {entry.resource}
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                      {entry.ip_address || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {/* Pagination */}
            {pagination && pagination.pages > 1 && (
              <div className="flex items-center justify-between border-t border-border px-4 py-3">
                <p className="text-xs text-muted-foreground">
                  Page {pagination.page} of {pagination.pages} ({pagination.total} entries)
                </p>
                <div className="flex gap-2">
                  <button
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page <= 1}
                    className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Previous
                  </button>
                  <button
                    onClick={() =>
                      setPage((p) => Math.min(pagination.pages, p + 1))
                    }
                    disabled={page >= pagination.pages}
                    className="rounded-md border border-border px-3 py-1 text-xs font-medium text-foreground hover:bg-muted disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
