const getBaseUrl = () => {
  if (typeof window !== "undefined") {
    const fromStorage = localStorage.getItem("asahi_api_url") || "";
    const fromEnv = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
    return (fromStorage || fromEnv || "").replace(/\/$/, "");
  }
  return (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");
};

function getAuthHeaders(): HeadersInit {
  const key =
    typeof window !== "undefined"
      ? localStorage.getItem("asahi_api_key") || process.env.NEXT_PUBLIC_API_KEY || ""
      : process.env.NEXT_PUBLIC_API_KEY || "";
  const h: HeadersInit = { "Content-Type": "application/json" };
  if (key) (h as Record<string, string>)["Authorization"] = `Bearer ${key}`;
  return h;
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const base = getBaseUrl();
  const url = path.startsWith("http") ? path : `${base}${path}`;
  const res = await fetch(url, {
    ...options,
    headers: { ...getAuthHeaders(), ...(options.headers as object) },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  if (res.headers.get("content-type")?.includes("application/json"))
    return res.json() as Promise<T>;
  return undefined as T;
}

export async function getMetrics(): Promise<Record<string, unknown>> {
  return apiFetch<Record<string, unknown>>("/metrics");
}

export async function getCostSummary(period = "24h"): Promise<{ data: Record<string, unknown> }> {
  return apiFetch<{ data: Record<string, unknown> }>(`/analytics/cost-summary?period=${period}`);
}

export async function getRecentInferences(limit = 50): Promise<{
  data: { inferences: Array<Record<string, unknown>>; count: number };
}> {
  return apiFetch<{ data: { inferences: Array<Record<string, unknown>>; count: number } }>(
    `/analytics/recent-inferences?limit=${limit}`
  );
}

export async function getCachePerformance(): Promise<{ data: Record<string, unknown> }> {
  return apiFetch<{ data: Record<string, unknown> }>("/analytics/cache-performance");
}

export async function getCostBreakdown(
  period = "day",
  groupBy = "model"
): Promise<{ data: unknown }> {
  return apiFetch<{ data: unknown }>(
    `/analytics/cost-breakdown?period=${period}&group_by=${groupBy}`
  );
}

export async function getTrends(
  metric = "cost",
  period = "day",
  intervals = 30
): Promise<{ data: unknown }> {
  return apiFetch<{ data: unknown }>(
    `/analytics/trends?metric=${metric}&period=${period}&intervals=${intervals}`
  );
}

export interface InferRequest {
  prompt: string;
  routing_mode?: "autopilot" | "guided" | "explicit";
  latency_budget_ms?: number;
  quality_threshold?: number;
  model_override?: string;
  organization_id?: string;
}

export interface InferResponse {
  request_id: string;
  response: string;
  model_used: string;
  tokens_input: number;
  tokens_output: number;
  cost: number;
  latency_ms: number;
  cache_hit: boolean;
  cache_tier?: number;
  routing_reason?: string;
  cost_original?: number;
  cost_savings_percent?: number;
  optimization_techniques?: string[];
}

export async function infer(body: InferRequest): Promise<InferResponse> {
  return apiFetch<InferResponse>("/infer", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function signup(orgName: string, userId: string, email?: string) {
  const base = getBaseUrl();
  const url = `${base}/signup`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ org_name: orgName, user_id: userId, email: email || null }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error((err as { detail?: string }).detail || res.statusText);
  }
  return res.json() as Promise<{
    org_id: string;
    api_key: string;
    org_name: string;
    message: string;
  }>;
}

export function getBaseUrlClient(): string {
  return getBaseUrl();
}
