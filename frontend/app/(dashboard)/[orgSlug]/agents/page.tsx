"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listAgents, createAgent, updateAgent, archiveAgent, type AgentItem } from "@/lib/api";
import { Archive, Bot, Pencil, Plus, Power, PowerOff, X } from "lucide-react";

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
  const [editAgent, setEditAgent] = useState<AgentItem | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<AgentItem | null>(null);
  const [form, setForm] = useState({
    name: "",
    description: "",
    routing_mode: "AUTO" as string,
    intervention_mode: "OBSERVE" as string,
  });
  const [editForm, setEditForm] = useState({
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

  const editMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Parameters<typeof updateAgent>[1] }) =>
      updateAgent(id, data, undefined, orgSlug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents", orgSlug] });
      setEditAgent(null);
    },
  });

  const archiveMutation = useMutation({
    mutationFn: (agentId: string) => archiveAgent(agentId, undefined, orgSlug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents", orgSlug] });
      setArchiveTarget(null);
    },
  });

  const openEdit = (agent: AgentItem) => {
    setEditForm({
      name: agent.name,
      description: agent.description || "",
      routing_mode: agent.routing_mode,
      intervention_mode: agent.intervention_mode,
    });
    setEditAgent(agent);
  };

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
      ) : agents.length === 0 && !showCreate ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 p-12 text-center">
          <div className="mb-4 inline-flex h-16 w-16 items-center justify-center rounded-full bg-asahio/10">
            <Bot className="h-8 w-8 text-asahio" />
          </div>
          <h3 className="mb-2 text-lg font-semibold text-foreground">No agents yet</h3>
          <p className="mb-6 max-w-md text-sm text-muted-foreground">
            Agents track calls, modes, and behavioral patterns. Create your first agent to start routing LLM traffic through ASAHIO.
          </p>

          <div className="mb-6 w-full max-w-xl rounded-lg border border-border bg-card overflow-hidden">
            <div className="border-b border-border bg-muted/50 px-4 py-2 text-left">
              <span className="text-xs font-medium text-muted-foreground">python</span>
            </div>
            <pre className="overflow-x-auto p-4 text-left">
              <code className="text-xs font-mono text-foreground">{`from asahio import AsahioClient

client = AsahioClient(api_key="your-key")

# Create an agent via SDK
agent = client.agents.create(
    name="My Agent",
    routing_mode="AUTO",
    intervention_mode="ASSISTED"
)

# Use it in requests
resp = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello"}],
    agent_id=agent.id
)`}</code>
            </pre>
          </div>

          <button
            onClick={() => setShowCreate(true)}
            className="rounded-lg bg-asahio px-6 py-2.5 text-sm font-medium text-white hover:bg-asahio-dark transition-colors"
          >
            Create Your First Agent
          </button>
          <a
            href="/docs"
            className="mt-3 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            View documentation →
          </a>
        </div>
      ) : agents.length === 0 ? null : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border bg-muted/50">
              <tr>
                <th className="px-4 py-3 font-medium text-muted-foreground">Name</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Agent ID</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Slug</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Routing</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Intervention</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Created</th>
                <th className="px-4 py-3 font-medium text-muted-foreground">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {agents.map((agent) => (
                <tr key={agent.id} className={`hover:bg-muted/30 transition-colors ${!agent.is_active ? "opacity-50" : ""}`}>
                  <td className="px-4 py-3 font-medium">
                    <Link
                      href={`/${orgSlug}/agents/${agent.id}`}
                      className="text-foreground hover:text-asahio transition-colors"
                    >
                      {agent.name}
                    </Link>
                    {!agent.is_active && (
                      <span className="ml-2 inline-block rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
                        Archived
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground select-all">{agent.id}</td>
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
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => openEdit(agent)}
                        className="rounded p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        title="Edit"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      {agent.is_active && (
                        <button
                          onClick={() => setArchiveTarget(agent)}
                          className="rounded p-1.5 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 transition-colors"
                          title="Archive"
                        >
                          <Archive className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Edit Modal */}
      {editAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-xl">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-foreground">Edit Agent</h2>
              <button onClick={() => setEditAgent(null)} className="text-muted-foreground hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">Name</label>
                <input
                  type="text"
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">Description</label>
                <input
                  type="text"
                  value={editForm.description}
                  onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-muted-foreground mb-1">Routing Mode</label>
                  <select
                    value={editForm.routing_mode}
                    onChange={(e) => setEditForm({ ...editForm, routing_mode: e.target.value })}
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
                    value={editForm.intervention_mode}
                    onChange={(e) => setEditForm({ ...editForm, intervention_mode: e.target.value })}
                    className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                  >
                    {INTERVENTION_MODES.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setEditAgent(null)}
                className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={() =>
                  editMutation.mutate({
                    id: editAgent.id,
                    data: {
                      name: editForm.name,
                      description: editForm.description || undefined,
                      routing_mode: editForm.routing_mode,
                      intervention_mode: editForm.intervention_mode,
                    },
                  })
                }
                disabled={!editForm.name || editMutation.isPending}
                className="rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white hover:bg-asahio-dark disabled:opacity-50"
              >
                {editMutation.isPending ? "Saving..." : "Save Changes"}
              </button>
            </div>
            {editMutation.isError && (
              <p className="mt-2 text-sm text-red-500">{String(editMutation.error)}</p>
            )}
          </div>
        </div>
      )}

      {/* Archive Confirmation */}
      {archiveTarget && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-sm rounded-lg border border-border bg-card p-6 shadow-xl">
            <h2 className="text-lg font-semibold text-foreground mb-2">Archive Agent</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Are you sure you want to archive <strong className="text-foreground">{archiveTarget.name}</strong>? The agent will be deactivated and no longer receive traffic.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setArchiveTarget(null)}
                className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-muted"
              >
                Cancel
              </button>
              <button
                onClick={() => archiveMutation.mutate(archiveTarget.id)}
                disabled={archiveMutation.isPending}
                className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {archiveMutation.isPending ? "Archiving..." : "Archive"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
