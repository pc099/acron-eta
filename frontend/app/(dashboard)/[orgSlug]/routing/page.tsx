"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getRoutingDecisions, listAgents, type RoutingDecisionItem } from "@/lib/api";
import { GitBranch, ChevronDown, ChevronRight } from "lucide-react";

const MODE_BADGE: Record<string, string> = {
  AUTO: "bg-emerald-500/20 text-emerald-400",
  EXPLICIT: "bg-blue-500/20 text-blue-400",
  GUIDED: "bg-amber-500/20 text-amber-400",
};

export default function RoutingPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : "";

  const [agentFilter, setAgentFilter] = useState<string>("");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const { data: agentsData } = useQuery({
    queryKey: ["agents", orgSlug],
    queryFn: () => listAgents(undefined, orgSlug),
    enabled: !!orgSlug,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["routing-decisions", orgSlug, agentFilter],
    queryFn: () =>
      getRoutingDecisions(
        { agent_id: agentFilter || undefined, limit: 50 },
        undefined,
        orgSlug,
      ),
    enabled: !!orgSlug,
  });

  const decisions = data?.data ?? [];
  const agents = agentsData?.data ?? [];

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Routing Decisions</h1>
          <p className="text-sm text-muted-foreground">
            Audit trail of how ASAHIO selected models for each request.
          </p>
        </div>
        <select
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="rounded-md border border-border bg-background px-3 py-1.5 text-sm text-foreground"
        >
          <option value="">All Agents</option>
          {agents.map((a) => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">Loading decisions...</div>
      ) : decisions.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <GitBranch className="h-12 w-12 text-muted-foreground/50" />
          <p className="mt-4 text-sm text-muted-foreground">No routing decisions recorded yet.</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="w-8 px-2 py-3"></th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Time</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Routing Mode</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Selected Model</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Provider</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Confidence</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Summary</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {decisions.map((d) => (
                <DecisionRow
                  key={d.id}
                  decision={d}
                  expanded={expandedId === d.id}
                  onToggle={() => setExpandedId(expandedId === d.id ? null : d.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DecisionRow({
  decision: d,
  expanded,
  onToggle,
}: {
  decision: RoutingDecisionItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer hover:bg-muted/30 transition-colors"
      >
        <td className="px-2 py-3 text-muted-foreground">
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </td>
        <td className="px-4 py-3 text-muted-foreground whitespace-nowrap">
          {new Date(d.created_at).toLocaleString()}
        </td>
        <td className="px-4 py-3">
          {d.routing_mode && (
            <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${MODE_BADGE[d.routing_mode] ?? "bg-muted text-muted-foreground"}`}>
              {d.routing_mode}
            </span>
          )}
        </td>
        <td className="px-4 py-3 font-mono text-xs text-foreground">{d.selected_model ?? "-"}</td>
        <td className="px-4 py-3 text-muted-foreground">{d.selected_provider ?? "-"}</td>
        <td className="px-4 py-3">
          {d.confidence != null ? (
            <div className="flex items-center gap-2">
              <div className="h-1.5 w-16 rounded-full bg-muted">
                <div
                  className="h-1.5 rounded-full bg-asahio"
                  style={{ width: `${Math.round(d.confidence * 100)}%` }}
                />
              </div>
              <span className="text-xs text-muted-foreground">{(d.confidence * 100).toFixed(0)}%</span>
            </div>
          ) : (
            "-"
          )}
        </td>
        <td className="px-4 py-3 text-muted-foreground truncate max-w-[200px]">
          {d.decision_summary ?? "-"}
        </td>
      </tr>
      {expanded && (
        <tr className="bg-muted/20">
          <td colSpan={7} className="px-8 py-4">
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-3">
                <div>
                  <span className="text-muted-foreground">Agent ID</span>
                  <p className="font-mono text-xs text-foreground">{d.agent_id ?? "-"}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Call Trace ID</span>
                  <p className="font-mono text-xs text-foreground">{d.call_trace_id ?? "-"}</p>
                </div>
                <div>
                  <span className="text-muted-foreground">Intervention Mode</span>
                  <p className="text-foreground">{d.intervention_mode ?? "-"}</p>
                </div>
              </div>
              {Object.keys(d.factors).length > 0 && (
                <div>
                  <span className="text-sm text-muted-foreground">Decision Factors</span>
                  <pre className="mt-1 overflow-x-auto rounded-md border border-border bg-background p-3 text-xs text-foreground">
                    {JSON.stringify(d.factors, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}
