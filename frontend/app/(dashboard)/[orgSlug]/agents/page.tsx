"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listAgents, createAgent, type AgentItem } from "@/lib/api";
import { Bot, Plus, Power, PowerOff } from "lucide-react";

const ROUTING_MODES = ["AUTO", "EXPLICIT", "GUIDED"] as const;
const INTERVENTION_MODES = ["OBSERVE", "ASSISTED", "AUTONOMOUS"] as const;

const MODE_BADGE: Record<string, string> = {
  AUTO: "bg-emerald-500/20 text-emerald-400",
  EXPLICIT: "bg-blue-500/20 text-blue-400",
  GUIDED: "bg-amber-500/20 text-amber-400",
  OBSERVE: "bg-slate-500/20 text-slate-400",
  ASSISTED: "bg-violet-500/20 text-violet-400",
  AUTONOMOUS: "bg-rose-500/20 text-rose-400",
};

export default function AgentsPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : "";
  const queryClient = useQueryClient();

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({
    name: "",
    description: "",
    routing_mode: "AUTO" as string,
    intervention_mode: "OBSERVE" as string,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["agents", orgSlug],
    queryFn: () => listAgents(undefined, orgSlug),
    enabled: !!orgSlug,
  });

  const agents: AgentItem[] = data?.data ?? [];

  const createMutation = useMutation({
    mutationFn: (body: Parameters<typeof createAgent>[0]) =>
      createAgent(body, undefined, orgSlug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents", orgSlug] });
      setShowCreate(false);
      setForm({ name: "", description: "", routing_mode: "AUTO", intervention_mode: "OBSERVE" });
    },
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Agents</h1>
          <p className="text-sm text-muted-foreground">
            Manage your AI agents and their routing configuration.
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-asahio-dark"
        >
          <Plus className="h-4 w-4" />
          Create Agent
        </button>
      </div>

      {showCreate && (
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-foreground mb-4">New Agent</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="My Agent"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Description</label>
              <input
                type="text"
                value={form.description}
                onChange={(e) => setForm({ ...form, description: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="Optional description"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Routing Mode</label>
              <select
                value={form.routing_mode}
                onChange={(e) => setForm({ ...form, routing_mode: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                {ROUTING_MODES.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Intervention Mode</label>
              <select
                value={form.intervention_mode}
                onChange={(e) => setForm({ ...form, intervention_mode: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                {INTERVENTION_MODES.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => createMutation.mutate(form)}
              disabled={!form.name || createMutation.isPending}
              className="rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-asahio-dark disabled:opacity-50"
            >
              {createMutation.isPending ? "Creating..." : "Create"}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              Cancel
            </button>
          </div>
          {createMutation.isError && (
            <p className="mt-2 text-sm text-red-500">{String(createMutation.error)}</p>
          )}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">Loading agents...</div>
      ) : agents.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <Bot className="h-12 w-12 text-muted-foreground/50" />
          <p className="mt-4 text-sm text-muted-foreground">No agents configured yet.</p>
          <button
            onClick={() => setShowCreate(true)}
            className="mt-2 text-sm font-medium text-asahio hover:underline"
          >
            Create your first agent
          </button>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Slug</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Routing</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Intervention</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {agents.map((agent) => (
                <tr key={agent.id} className="hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 font-medium text-foreground">{agent.name}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{agent.slug}</td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${MODE_BADGE[agent.routing_mode] ?? ""}`}>
                      {agent.routing_mode}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${MODE_BADGE[agent.intervention_mode] ?? ""}`}>
                      {agent.intervention_mode}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {agent.is_active ? (
                      <span className="flex items-center gap-1 text-emerald-400">
                        <Power className="h-3 w-3" /> Active
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-muted-foreground">
                        <PowerOff className="h-3 w-3" /> Inactive
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(agent.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
