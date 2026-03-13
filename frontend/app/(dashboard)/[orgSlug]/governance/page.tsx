"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getAuditLog, getOrgMembers, type AuditLogEntry, type MemberResponse } from "@/lib/api";
import { Shield, ScrollText, Users } from "lucide-react";
import { cn } from "@/lib/utils";

const TABS = [
  { id: "audit", label: "Audit Log", icon: ScrollText },
  { id: "members", label: "Members", icon: Users },
] as const;

const ROLE_BADGE: Record<string, string> = {
  OWNER: "bg-asahio/20 text-asahio",
  ADMIN: "bg-violet-500/20 text-violet-400",
  MEMBER: "bg-blue-500/20 text-blue-400",
  VIEWER: "bg-slate-500/20 text-slate-400",
};

export default function GovernancePage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : "";
  const [tab, setTab] = useState<"audit" | "members">("audit");
  const [auditPage, setAuditPage] = useState(1);

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Governance</h1>
        <p className="text-sm text-muted-foreground">
          Audit logs, team members, and access controls.
        </p>
      </div>

      <div className="flex gap-1 border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id as "audit" | "members")}
            className={cn(
              "flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors",
              tab === t.id
                ? "border-asahio text-asahio"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            <t.icon className="h-4 w-4" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "audit" ? (
        <AuditTab orgSlug={orgSlug} page={auditPage} onPageChange={setAuditPage} />
      ) : (
        <MembersTab orgSlug={orgSlug} />
      )}
    </div>
  );
}

function AuditTab({
  orgSlug,
  page,
  onPageChange,
}: {
  orgSlug: string;
  page: number;
  onPageChange: (p: number) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["audit", orgSlug, page],
    queryFn: () => getAuditLog({ page, limit: 25 }, undefined, orgSlug),
    enabled: !!orgSlug,
  });

  const entries = data?.data ?? [];
  const pagination = data?.pagination;

  if (isLoading) {
    return <div className="flex items-center justify-center py-12 text-muted-foreground">Loading audit log...</div>;
  }

  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
        <Shield className="h-12 w-12 text-muted-foreground/50" />
        <p className="mt-4 text-sm text-muted-foreground">No audit entries yet.</p>
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-4 py-3 font-medium text-muted-foreground">Time</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Actor</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Action</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">Resource</th>
              <th className="px-4 py-3 font-medium text-muted-foreground">IP Address</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {entries.map((e) => (
              <tr key={e.id} className="hover:bg-muted/30 transition-colors">
                <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
                  {new Date(e.timestamp).toLocaleString()}
                </td>
                <td className="px-4 py-3 text-foreground">{e.actor}</td>
                <td className="px-4 py-3">
                  <span className="inline-block rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-foreground">
                    {e.action}
                  </span>
                </td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{e.resource}</td>
                <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                  {e.ip_address ?? "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {pagination && pagination.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>Page {pagination.page} of {pagination.pages}</span>
          <div className="flex gap-2">
            <button
              onClick={() => onPageChange(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="rounded-md border border-border px-3 py-1 text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              Previous
            </button>
            <button
              onClick={() => onPageChange(page + 1)}
              disabled={page >= pagination.pages}
              className="rounded-md border border-border px-3 py-1 text-foreground transition-colors hover:bg-muted disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </>
  );
}

function MembersTab({ orgSlug }: { orgSlug: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["members", orgSlug],
    queryFn: () => getOrgMembers(orgSlug),
    enabled: !!orgSlug,
  });

  const members = data ?? [];

  if (isLoading) {
    return <div className="flex items-center justify-center py-12 text-muted-foreground">Loading members...</div>;
  }

  if (members.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
        <Users className="h-12 w-12 text-muted-foreground/50" />
        <p className="mt-4 text-sm text-muted-foreground">No members found.</p>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border bg-muted/50">
          <tr>
            <th className="px-4 py-3 font-medium text-muted-foreground">Email</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">Name</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">Role</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">Joined</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {members.map((m) => (
            <tr key={m.user_id} className="hover:bg-muted/30 transition-colors">
              <td className="px-4 py-3 text-foreground">{m.email}</td>
              <td className="px-4 py-3 text-muted-foreground">{m.name ?? "-"}</td>
              <td className="px-4 py-3">
                <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${ROLE_BADGE[m.role.toUpperCase()] ?? "bg-muted text-muted-foreground"}`}>
                  {m.role}
                </span>
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {new Date(m.joined_at).toLocaleDateString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
