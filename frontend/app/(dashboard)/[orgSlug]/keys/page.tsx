"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listKeys, createKey, revokeKey } from "@/lib/api";
import type { ApiKeyCreateResponse } from "@/lib/api";
import { Copy, Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export default function KeysPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : undefined;
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(new Set());

  const { data: keys, isLoading } = useQuery({
    queryKey: ["keys", orgSlug],
    queryFn: () => listKeys(undefined, orgSlug),
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createKey({ name }, undefined, orgSlug),
    onSuccess: (data) => {
      setCreatedKey(data);
      setNewKeyName("");
      queryClient.invalidateQueries({ queryKey: ["keys"] });
      toast.success("API key created");
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Failed to create key";
      toast.error(msg);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (keyId: string) => revokeKey(keyId, undefined, orgSlug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["keys"] });
      toast.success("API key revoked");
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "Failed to revoke key";
      toast.error(msg);
    },
  });

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    toast.success("Copied to clipboard");
  };

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">API Keys</h1>
          <p className="text-sm text-muted-foreground">
            Manage your API keys for programmatic access
          </p>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="inline-flex items-center gap-2 rounded-md bg-asahi px-4 py-2 text-sm font-medium text-white hover:bg-asahi-dark transition-colors"
        >
          <Plus className="h-4 w-4" />
          Create Key
        </button>
      </div>

      {/* Warning */}
      <div className="rounded-md border border-yellow-500/30 bg-yellow-500/10 p-4">
        <p className="text-sm text-yellow-200">
          Never share your secret API keys in publicly accessible areas such as
          GitHub, client-side code, or public repositories.
        </p>
      </div>

      {/* Created key modal */}
      {createdKey && (
        <div className="rounded-lg border-2 border-asahi bg-asahi/10 p-6">
          <h3 className="text-lg font-bold text-asahi">
            Save your API key now
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            This key will not be shown again. Copy it now.
          </p>
          <div className="mt-4 flex items-center gap-2">
            <code className="flex-1 rounded-md border border-border bg-muted px-4 py-3 font-mono text-sm text-foreground">
              {createdKey.raw_key}
            </code>
            <button
              onClick={() => copyToClipboard(createdKey.raw_key)}
              className="rounded-md border border-border p-3 hover:bg-muted transition-colors"
            >
              <Copy className="h-4 w-4" />
            </button>
          </div>
          <button
            onClick={() => setCreatedKey(null)}
            className="mt-4 text-sm text-muted-foreground hover:text-foreground"
          >
            I've copied my key
          </button>
        </div>
      )}

      {/* Create form */}
      {showCreate && !createdKey && (
        <div className="rounded-lg border border-border bg-card p-6">
          <h3 className="text-sm font-semibold text-foreground">
            Create New API Key
          </h3>
          <div className="mt-4 flex items-center gap-3">
            <input
              type="text"
              placeholder="Key name (e.g., Production, Staging)"
              value={newKeyName}
              onChange={(e) => setNewKeyName(e.target.value)}
              className="flex-1 rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-asahi"
            />
            <button
              onClick={() => {
                if (newKeyName.trim()) createMutation.mutate(newKeyName.trim());
              }}
              disabled={!newKeyName.trim() || createMutation.isPending}
              className="rounded-md bg-asahi px-4 py-2 text-sm font-medium text-white hover:bg-asahi-dark disabled:opacity-50 transition-colors"
            >
              {createMutation.isPending ? "Creating..." : "Create"}
            </button>
            <button
              onClick={() => setShowCreate(false)}
              className="rounded-md border border-border px-4 py-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Keys table */}
      <div className="rounded-lg border border-border bg-card shadow-sm">
        {isLoading ? (
          <div className="animate-pulse space-y-4 p-6">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded bg-muted" />
            ))}
          </div>
        ) : !keys || keys.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
            No API keys yet. Create one to get started.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Key</th>
                <th className="px-4 py-3">Created</th>
                <th className="px-4 py-3">Last Used</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Actions</th>
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => (
                <tr
                  key={key.id}
                  className="border-b border-border last:border-0"
                >
                  <td className="px-4 py-3 font-medium text-foreground">
                    {key.name}
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                      {key.environment}
                    </span>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs">
                    {revealedKeys.has(key.id)
                      ? `${key.prefix}...${key.last_four}`
                      : `asahi_****${key.last_four}`}
                    <button
                      onClick={() => {
                        const next = new Set(revealedKeys);
                        if (next.has(key.id)) next.delete(key.id);
                        else next.add(key.id);
                        setRevealedKeys(next);
                      }}
                      className="ml-2 text-muted-foreground hover:text-foreground"
                    >
                      {revealedKeys.has(key.id) ? (
                        <EyeOff className="inline h-3 w-3" />
                      ) : (
                        <Eye className="inline h-3 w-3" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(key.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {key.last_used_at
                      ? new Date(key.last_used_at).toLocaleDateString()
                      : "Never"}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={cn(
                        "rounded-full px-2 py-0.5 text-xs font-medium",
                        key.is_active
                          ? "bg-green-500/20 text-green-400"
                          : "bg-red-500/20 text-red-400"
                      )}
                    >
                      {key.is_active ? "Active" : "Revoked"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {key.is_active && (
                      <button
                        onClick={() => {
                          if (confirm(`Revoke key "${key.name}"?`))
                            revokeMutation.mutate(key.id);
                        }}
                        className="text-muted-foreground hover:text-red-400 transition-colors"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
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
