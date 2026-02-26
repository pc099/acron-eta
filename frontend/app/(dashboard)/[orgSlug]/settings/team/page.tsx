"use client";

import { useQuery } from "@tanstack/react-query";
import { getOrgMembers } from "@/lib/api";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { Users } from "lucide-react";

const roleColors: Record<string, string> = {
  owner: "bg-asahi/20 text-asahi",
  admin: "bg-blue-500/20 text-blue-400",
  member: "bg-muted text-muted-foreground",
};

export default function TeamPage({
  params,
}: {
  params: { orgSlug: string };
}) {
  const { data: members, isLoading } = useQuery({
    queryKey: ["org-members", params.orgSlug],
    queryFn: () => getOrgMembers(params.orgSlug),
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Team</h1>
        <p className="text-sm text-muted-foreground">
          View team members in your organisation
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
        <div className="border-b-2 border-asahi px-4 py-2 text-sm font-medium text-asahi">
          Team
        </div>
        <Link
          href={`/${params.orgSlug}/settings/security`}
          className="px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground transition-colors"
        >
          Security
        </Link>
      </div>

      {/* Members table */}
      <div className="rounded-lg border border-border bg-card shadow-sm">
        {isLoading ? (
          <div className="animate-pulse space-y-4 p-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded bg-muted" />
            ))}
          </div>
        ) : !members || members.length === 0 ? (
          <div className="flex h-48 flex-col items-center justify-center gap-3">
            <Users className="h-8 w-8 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No team members found.
            </p>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-3">Member</th>
                <th className="px-4 py-3">Email</th>
                <th className="px-4 py-3">Role</th>
                <th className="px-4 py-3">Joined</th>
              </tr>
            </thead>
            <tbody>
              {members.map((member) => (
                <tr
                  key={member.user_id}
                  className="border-b border-border last:border-0 hover:bg-muted/50 transition-colors"
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <div className="flex h-8 w-8 items-center justify-center rounded-full bg-asahi/20 text-xs font-medium text-asahi">
                        {(member.name || member.email)
                          .charAt(0)
                          .toUpperCase()}
                      </div>
                      <span className="font-medium text-foreground">
                        {member.name || "-"}
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {member.email}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize",
                        roleColors[member.role] || roleColors.member
                      )}
                    >
                      {member.role}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(member.joined_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
