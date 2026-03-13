"use client";

import { useState } from "react";
import { useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  listModelEndpoints,
  registerModelEndpoint,
  type ModelEndpointItem,
} from "@/lib/api";
import { Server, Plus, Circle } from "lucide-react";

const PROVIDERS = ["openai", "anthropic", "cohere", "google", "custom"] as const;
const ENDPOINT_TYPES = ["PLATFORM", "BYOM"] as const;

const HEALTH_DOT: Record<string, string> = {
  healthy: "text-emerald-400",
  degraded: "text-amber-400",
  unreachable: "text-red-400",
  unknown: "text-muted-foreground",
};

export default function ModelsPage() {
  const params = useParams();
  const orgSlug = typeof params?.orgSlug === "string" ? params.orgSlug : "";
  const queryClient = useQueryClient();

  const [showRegister, setShowRegister] = useState(false);
  const [form, setForm] = useState({
    name: "",
    provider: "openai" as string,
    model_id: "",
    endpoint_type: "PLATFORM" as string,
    endpoint_url: "",
    fallback_model_id: "",
    validate_health: false,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["models", orgSlug],
    queryFn: () => listModelEndpoints(undefined, orgSlug),
    enabled: !!orgSlug,
  });

  const endpoints = data?.data ?? [];

  const registerMutation = useMutation({
    mutationFn: (body: Parameters<typeof registerModelEndpoint>[0]) =>
      registerModelEndpoint(body, undefined, orgSlug),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models", orgSlug] });
      setShowRegister(false);
      setForm({
        name: "", provider: "openai", model_id: "", endpoint_type: "PLATFORM",
        endpoint_url: "", fallback_model_id: "", validate_health: false,
      });
    },
  });

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Model Endpoints</h1>
          <p className="text-sm text-muted-foreground">
            Register and manage LLM model endpoints for routing.
          </p>
        </div>
        <button
          onClick={() => setShowRegister(true)}
          className="flex items-center gap-2 rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-asahio-dark"
        >
          <Plus className="h-4 w-4" />
          Register Endpoint
        </button>
      </div>

      {showRegister && (
        <div className="rounded-lg border border-border bg-card p-6 shadow-sm">
          <h2 className="text-lg font-semibold text-foreground mb-4">Register Model Endpoint</h2>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Name</label>
              <input
                type="text"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="GPT-4 Production"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Provider</label>
              <select
                value={form.provider}
                onChange={(e) => setForm({ ...form, provider: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                {PROVIDERS.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Model ID</label>
              <input
                type="text"
                value={form.model_id}
                onChange={(e) => setForm({ ...form, model_id: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="gpt-4-turbo"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Endpoint Type</label>
              <select
                value={form.endpoint_type}
                onChange={(e) => setForm({ ...form, endpoint_type: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                {ENDPOINT_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            {form.endpoint_type === "BYOM" && (
              <div className="md:col-span-2">
                <label className="block text-sm font-medium text-muted-foreground mb-1">Endpoint URL</label>
                <input
                  type="url"
                  value={form.endpoint_url}
                  onChange={(e) => setForm({ ...form, endpoint_url: e.target.value })}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                  placeholder="https://your-model-endpoint.com/v1"
                />
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-muted-foreground mb-1">Fallback Model ID</label>
              <input
                type="text"
                value={form.fallback_model_id}
                onChange={(e) => setForm({ ...form, fallback_model_id: e.target.value })}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground"
                placeholder="Optional"
              />
            </div>
            <div className="flex items-center gap-2 pt-6">
              <input
                type="checkbox"
                id="validate-health"
                checked={form.validate_health}
                onChange={(e) => setForm({ ...form, validate_health: e.target.checked })}
                className="rounded border-border"
              />
              <label htmlFor="validate-health" className="text-sm text-muted-foreground">
                Validate health on registration
              </label>
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() =>
                registerMutation.mutate({
                  name: form.name,
                  provider: form.provider,
                  model_id: form.model_id,
                  endpoint_type: form.endpoint_type,
                  endpoint_url: form.endpoint_url || undefined,
                  fallback_model_id: form.fallback_model_id || undefined,
                  validate_health: form.validate_health,
                })
              }
              disabled={!form.name || !form.model_id || registerMutation.isPending}
              className="rounded-md bg-asahio px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-asahio-dark disabled:opacity-50"
            >
              {registerMutation.isPending ? "Registering..." : "Register"}
            </button>
            <button
              onClick={() => setShowRegister(false)}
              className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              Cancel
            </button>
          </div>
          {registerMutation.isError && (
            <p className="mt-2 text-sm text-red-500">{String(registerMutation.error)}</p>
          )}
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-muted-foreground">Loading endpoints...</div>
      ) : endpoints.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-12">
          <Server className="h-12 w-12 text-muted-foreground/50" />
          <p className="mt-4 text-sm text-muted-foreground">No model endpoints registered.</p>
          <button
            onClick={() => setShowRegister(true)}
            className="mt-2 text-sm font-medium text-asahio hover:underline"
          >
            Register your first endpoint
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {endpoints.map((ep) => (
            <div
              key={ep.id}
              className="rounded-lg border border-border bg-card p-5 shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-semibold text-foreground">{ep.name}</h3>
                  <p className="font-mono text-xs text-muted-foreground mt-1">{ep.model_id}</p>
                </div>
                <Circle
                  className={`h-3 w-3 fill-current ${HEALTH_DOT[ep.health_status] ?? HEALTH_DOT.unknown}`}
                />
              </div>
              <div className="mt-4 space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Provider</span>
                  <span className="text-foreground">{ep.provider}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Type</span>
                  <span className="text-foreground">{ep.endpoint_type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Health</span>
                  <span className={HEALTH_DOT[ep.health_status] ?? "text-muted-foreground"}>
                    {ep.health_status}
                  </span>
                </div>
                {ep.fallback_model_id && (
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Fallback</span>
                    <span className="font-mono text-xs text-foreground">{ep.fallback_model_id}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Status</span>
                  <span className={ep.is_active ? "text-emerald-400" : "text-muted-foreground"}>
                    {ep.is_active ? "Active" : "Inactive"}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
