"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { listKeys, createKey, revokeKey } from "@/lib/api";
import type { ApiKeyCreateResponse } from "@/lib/api";
import { Copy, Eye, EyeOff, Plus, Trash2, AlertTriangle, X } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";

export default function KeysPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : undefined;
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [createdKey, setCreatedKey] = useState<ApiKeyCreateResponse | null>(null);
  const [keyCopied, setKeyCopied] = useState(false);
  const [revealedKeys, setRevealedKeys] = useState<Set<string>>(new Set());

  const { data: keys, isLoading } = useQuery({
    queryKey: ["keys", orgSlug],
    queryFn: () => listKeys(undefined, orgSlug),
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createKey({ name }, undefined, orgSlug),
    onSuccess: (data) => {
      setCreatedKey(data);
      setKeyCopied(false);
      setNewKeyName("");
      setShowCreate(false);
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
          className="inline-flex items-center gap-2 rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white hover:bg-asahio-dark transition-colors"
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

      {/* Show-once modal for newly created key */}
      {createdKey && (
        <ShowOnceKeyModal
          keyData={createdKey}
          copied={keyCopied}
          onCopy={() => {
            copyToClipboard(createdKey.raw_key);
            setKeyCopied(true);
          }}
          onDismiss={() => setCreatedKey(null)}
        />
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
              onKeyDown={(e) => {
                if (e.key === "Enter" && newKeyName.trim())
                  createMutation.mutate(newKeyName.trim());
              }}
              className="flex-1 rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-asahio"
            />
            <button
              onClick={() => {
                if (newKeyName.trim()) createMutation.mutate(newKeyName.trim());
              }}
              disabled={!newKeyName.trim() || createMutation.isPending}
              className="rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white hover:bg-asahio-dark disabled:opacity-50 transition-colors"
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
                      : `asahio_****${key.last_four}`}
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

/* ── Show-Once Key Modal ───────────────────────── */

function ShowOnceKeyModal({
  keyData,
  copied,
  onCopy,
  onDismiss,
}: {
  keyData: ApiKeyCreateResponse;
  copied: boolean;
  onCopy: () => void;
  onDismiss: () => void;
}) {
  const [secondsLeft, setSecondsLeft] = useState(60);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    intervalRef.current = setInterval(() => {
      setSecondsLeft((s) => {
        if (s <= 1) {
          if (intervalRef.current) clearInterval(intervalRef.current);
          return 0;
        }
        return s - 1;
      });
    }, 1000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // Auto-dismiss when timer hits 0
  useEffect(() => {
    if (secondsLeft === 0) onDismiss();
  }, [secondsLeft, onDismiss]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-2xl animate-fade-in">
        {/* Timer badge */}
        <div className="absolute right-4 top-4 flex items-center gap-1.5">
          <div
            className={cn(
              "flex h-8 w-8 items-center justify-center rounded-full text-xs font-bold",
              secondsLeft <= 10
                ? "bg-red-500/20 text-red-400"
                : "bg-muted text-muted-foreground"
            )}
          >
            {secondsLeft}
          </div>
        </div>

        <h3 className="text-lg font-bold text-foreground">
          Your API Key
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Key <span className="font-medium text-foreground">{keyData.name}</span> has been created.
        </p>

        {/* Warning */}
        <div className="mt-4 flex items-start gap-3 rounded-md border border-orange-500/30 bg-orange-500/10 p-3">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-orange-400" />
          <p className="text-sm text-orange-200">
            This is the only time this key will be shown. Copy it now and store
            it in a secure location.
          </p>
        </div>

        {/* Key display */}
        <div className="mt-4 flex items-center gap-2">
          <code className="flex-1 overflow-x-auto rounded-md border border-border bg-background px-4 py-3 font-mono text-sm text-foreground">
            {keyData.raw_key}
          </code>
          <button
            onClick={onCopy}
            className={cn(
              "rounded-md border p-3 transition-colors",
              copied
                ? "border-green-500/50 bg-green-500/10 text-green-400"
                : "border-border text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <Copy className="h-4 w-4" />
          </button>
        </div>

        {/* Confirm button */}
        <button
          onClick={onDismiss}
          disabled={!copied}
          className={cn(
            "mt-6 w-full rounded-md px-4 py-2.5 text-sm font-medium transition-colors",
            copied
              ? "bg-asahio text-white hover:bg-asahio-dark"
              : "cursor-not-allowed bg-muted text-muted-foreground"
          )}
        >
          {copied ? "I've copied my key" : "Copy the key first to continue"}
        </button>

        {/* Progress bar */}
        <div className="mt-4 h-1 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-asahio transition-all duration-1000 ease-linear"
            style={{ width: `${(secondsLeft / 60) * 100}%` }}
          />
        </div>
      </div>
    </div>
  );
}
