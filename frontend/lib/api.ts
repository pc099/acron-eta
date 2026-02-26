/**
 * Typed API client for the ASAHI backend.
 * All endpoints return typed responses — no `any`.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ────────────────────────────────────

export interface OverviewResponse {
  period: string;
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_without_asahi: number;
  total_cost_with_asahi: number;
  total_savings_usd: number;
  average_savings_pct: number;
  cache_hit_rate: number;
  cache_hits: { tier1: number; tier2: number; tier3: number };
  avg_latency_ms: number;
  p99_latency_ms: number | null;
  savings_delta_pct: number;
  requests_delta_pct: number;
}

export interface SavingsDataPoint {
  timestamp: string;
  cost_without_asahi: number;
  cost_with_asahi: number;
  savings_usd: number;
  requests: number;
}

export interface ModelBreakdown {
  model: string;
  requests: number;
  total_cost: number;
  total_savings: number;
}

export interface RequestLogEntry {
  id: string;
  model_requested: string | null;
  model_used: string;
  provider: string | null;
  routing_mode: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_without_asahi: number;
  cost_with_asahi: number;
  savings_usd: number;
  savings_pct: number | null;
  cache_hit: boolean;
  cache_tier: string | null;
  latency_ms: number | null;
  status_code: number;
  created_at: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    page: number;
    limit: number;
    total: number;
    pages: number;
  };
}

export interface ApiKeyItem {
  id: string;
  name: string;
  environment: string;
  prefix: string;
  last_four: string;
  scopes: string[];
  allowed_models: string[] | null;
  is_active: boolean;
  last_used_at: string | null;
  created_at: string;
}

export interface ApiKeyCreateResponse {
  id: string;
  name: string;
  raw_key: string;
  prefix: string;
  last_four: string;
  environment: string;
  scopes: string[];
  created_at: string;
}

export interface OrgResponse {
  id: string;
  name: string;
  slug: string;
  plan: string;
  monthly_request_limit: number;
  monthly_token_limit: number;
  created_at: string;
}

export interface MemberResponse {
  user_id: string;
  email: string;
  name: string | null;
  role: string;
  joined_at: string;
}

export interface UsageResponse {
  period_start: string;
  total_requests: number;
  total_input_tokens: number;
  total_output_tokens: number;
  monthly_request_limit: number;
  monthly_token_limit: number;
  requests_pct: number;
  tokens_pct: number;
}

export interface CachePerformance {
  total_requests: number;
  cache_hit_rate: number;
  tiers: {
    exact: { hits: number; rate: number };
    semantic: { hits: number; rate: number };
    intermediate: { hits: number; rate: number };
  };
}

export interface LatencyPercentiles {
  p50: number;
  p90: number;
  p95: number;
  p99: number;
  avg: number;
}

export interface ForecastResponse {
  forecast_days: number;
  projected_cost_usd: number;
  projected_savings_usd: number;
  projected_requests: number;
  daily_avg_cost: number;
  daily_avg_savings: number;
}

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  actor: string;
  action: string;
  resource: string;
  ip_address: string | null;
}

export interface ChatCompletionResponse {
  id: string;
  object: string;
  model: string;
  choices: Array<{
    index: number;
    message: { role: string; content: string };
    finish_reason: string;
  }>;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
  };
  asahi: {
    cache_hit: boolean;
    cache_tier: string | null;
    model_requested: string | null;
    model_used: string;
    cost_without_asahi: number;
    cost_with_asahi: number;
    savings_usd: number;
    savings_pct: number;
    routing_reason: string;
  };
}

// ── API Client ───────────────────────────────

async function fetchApi<T>(
  path: string,
  options: RequestInit = {},
  token?: string
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, { ...options, headers });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`API Error ${response.status}: ${body}`);
  }

  return response.json() as Promise<T>;
}

// ── Auth ─────────────────────────────────────

export async function signup(data: {
  email: string;
  name?: string;
  clerk_user_id?: string;
  org_name?: string;
}) {
  return fetchApi<{ user_id: string; email: string; org_id: string; org_slug: string }>(
    "/auth/signup",
    { method: "POST", body: JSON.stringify(data) }
  );
}

export async function login(data: { clerk_user_id: string }) {
  return fetchApi<{
    user_id: string;
    email: string;
    name: string | null;
    organisations: Array<{
      org_id: string;
      org_slug: string;
      org_name: string;
      role: string;
      plan: string;
    }>;
  }>("/auth/login", { method: "POST", body: JSON.stringify(data) });
}

// ── Organisations ────────────────────────────

export async function getOrg(slug: string, token?: string) {
  return fetchApi<OrgResponse>(`/orgs/${slug}`, {}, token);
}

export async function getOrgMembers(slug: string, token?: string) {
  return fetchApi<MemberResponse[]>(`/orgs/${slug}/members`, {}, token);
}

export async function getOrgUsage(slug: string, token?: string) {
  return fetchApi<UsageResponse>(`/orgs/${slug}/usage`, {}, token);
}

// ── API Keys ─────────────────────────────────

export async function listKeys(token?: string) {
  return fetchApi<ApiKeyItem[]>("/keys", {}, token);
}

export async function createKey(
  data: { name: string; environment?: string; scopes?: string[] },
  token?: string
) {
  return fetchApi<ApiKeyCreateResponse>("/keys", {
    method: "POST",
    body: JSON.stringify(data),
  }, token);
}

export async function revokeKey(keyId: string, token?: string) {
  return fetchApi<void>(`/keys/${keyId}`, { method: "DELETE" }, token);
}

export async function rotateKey(keyId: string, token?: string) {
  return fetchApi<ApiKeyCreateResponse>(
    `/keys/${keyId}/rotate`,
    { method: "POST" },
    token
  );
}

// ── Analytics ────────────────────────────────

export async function getAnalyticsOverview(
  period: string = "30d",
  token?: string
) {
  return fetchApi<OverviewResponse>(
    `/analytics/overview?period=${period}`,
    {},
    token
  );
}

export async function getSavingsTimeSeries(
  period: string = "30d",
  granularity: string = "day",
  token?: string
) {
  return fetchApi<{ data: SavingsDataPoint[] }>(
    `/analytics/savings?period=${period}&granularity=${granularity}`,
    {},
    token
  );
}

export async function getModelBreakdown(
  period: string = "30d",
  token?: string
) {
  return fetchApi<{ data: ModelBreakdown[] }>(
    `/analytics/models?period=${period}`,
    {},
    token
  );
}

export async function getCachePerformance(
  period: string = "30d",
  token?: string
) {
  return fetchApi<CachePerformance>(
    `/analytics/cache?period=${period}`,
    {},
    token
  );
}

export async function getLatencyPercentiles(
  period: string = "30d",
  token?: string
) {
  return fetchApi<LatencyPercentiles>(
    `/analytics/latency?period=${period}`,
    {},
    token
  );
}

export async function getRequestLogs(
  params: {
    page?: number;
    limit?: number;
    model?: string;
    cache_hit?: boolean;
  } = {},
  token?: string
) {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.limit) searchParams.set("limit", String(params.limit));
  if (params.model) searchParams.set("model", params.model);
  if (params.cache_hit !== undefined)
    searchParams.set("cache_hit", String(params.cache_hit));
  return fetchApi<PaginatedResponse<RequestLogEntry>>(
    `/analytics/requests?${searchParams}`,
    {},
    token
  );
}

export async function getForecast(days: number = 30, token?: string) {
  return fetchApi<ForecastResponse>(
    `/analytics/forecast?days=${days}`,
    {},
    token
  );
}

// ── Audit ───────────────────────────────────

export async function getAuditLog(
  params: { page?: number; limit?: number } = {},
  token?: string
) {
  const searchParams = new URLSearchParams();
  if (params.page) searchParams.set("page", String(params.page));
  if (params.limit) searchParams.set("limit", String(params.limit));
  return fetchApi<PaginatedResponse<AuditLogEntry>>(
    `/governance/audit?${searchParams}`,
    {},
    token
  );
}

// ── Gateway ──────────────────────────────────

export async function chatCompletions(
  data: {
    model?: string;
    messages: Array<{ role: string; content: string }>;
    routing_mode?: string;
    quality_preference?: string;
    latency_preference?: string;
  },
  token?: string
) {
  return fetchApi<ChatCompletionResponse>(
    "/v1/chat/completions",
    { method: "POST", body: JSON.stringify(data) },
    token
  );
}
