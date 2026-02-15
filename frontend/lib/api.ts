const API_URL_STORAGE = "acron_api_url";
const API_KEY_STORAGE = "acron_api_key";

export function getBaseUrlClient(): string {
  if (typeof window === "undefined") return "";
  return (
    localStorage.getItem(API_URL_STORAGE) ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  );
}

export function getApiKeyClient(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

export async function login(data: { email: string; password: string }) {
  return fetchApi("/auth/login", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function signup(data: {
  email: string;
  password: string;
  full_name?: string;
  org_name?: string;
}) {
  return fetchApi("/auth/signup", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

/** Delete account; does not use API key (identity confirmed by email + password). */
export async function deleteAccount(data: { email: string; password: string }) {
  const baseUrl = getBaseUrlClient();
  const url = `${baseUrl.replace(/\/$/, "")}/auth/delete-account`;
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!response.ok) {
    const err = await response.text();
    throw new Error(err || "Failed to delete account");
  }
  return response.json();
}

async function fetchApi(endpoint: string, options: RequestInit = {}) {
  const baseUrl = getBaseUrlClient();
  const apiKey = getApiKeyClient();

  const url = `${baseUrl.replace(/\/$/, "")}${endpoint}`;
  const headers = {
    "Content-Type": "application/json",
    ...(apiKey ? { "x-api-key": apiKey } : {}),
    ...options.headers,
  };

  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const errorBody = await response.text();
    throw new Error(`API Error ${response.status}: ${errorBody}`);
  }
  return response.json();
}

export interface InferResponse {
  response: string;
  model_used: string;
  cost: number;
  latency_ms: number;
  cache_hit: boolean;
  cache_tier?: number;
  cost_savings_percent?: number;
}

export async function infer(data: {
  prompt: string;
  routing_mode: string;
  quality_threshold?: number;
  latency_budget_ms?: number;
  quality_preference?: string;
  latency_preference?: string;
  model_override?: string;
}) {
  return fetchApi("/infer", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getMetrics() {
  return fetchApi("/metrics");
}

export async function getCostSummary(period: string = "24h") {
  return fetchApi(`/analytics/cost-summary?period=${period}`);
}

export async function getRecentInferences(limit: number = 50) {
  return fetchApi(`/analytics/recent-inferences?limit=${limit}`);
}

export async function getCostBreakdown(period: string, groupBy: string) {
  return fetchApi(`/analytics/cost-breakdown?period=${period}&group_by=${groupBy}`);
}

export async function getTrends(metric: string, period: string, intervals: number) {
  return fetchApi(`/analytics/trends?metric=${metric}&period=${period}&intervals=${intervals}`);
}
