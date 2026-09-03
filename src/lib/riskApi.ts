const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const API_TOKEN = import.meta.env.VITE_API_TOKEN;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("accept", "application/json");
  if (API_TOKEN && !headers.has("authorization") && !headers.has("x-api-key")) {
    headers.set("authorization", `Bearer ${API_TOKEN}`);
  }
  if (init.body && !headers.has("content-type")) headers.set("content-type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Risk API offline");
  }

  const text = await response.text();
  let payload: unknown;
  try {
    payload = text ? (JSON.parse(text) as unknown) : undefined;
  } catch {
    payload = text;
  }

  if (!response.ok) {
    const message =
      typeof payload === "object" && payload !== null && "detail" in payload
        ? String(payload.detail)
        : typeof payload === "object" && payload !== null && "message" in payload
          ? String(payload.message)
          : text || response.statusText || "Risk API request failed";
    throw new ApiError(response.status, message);
  }
  return payload as T;
}

export interface RiskConfig {
  id: number;
  user_id: number;
  daily_loss_limit: number;
  cooldown_seconds: number;
  enabled_time_start: string;
  enabled_time_end: string;
  category_ceiling_politics: number;
  category_ceiling_sports: number;
  k_value: number;
  max_position_pct: number;
  trailing_stop_pct: number;
  enable_circuit_breaker: boolean;
  enable_time_window: boolean;
  enable_category_ceiling: boolean;
  enable_trailing_stop: boolean;
  updated_at?: string | null;
}

export type RiskConfigUpdate = Partial<Omit<RiskConfig, "id" | "user_id" | "updated_at">>;

export interface GateStatus {
  name: string;
  status: "OK" | "BLOCKED" | "WARN" | "DISABLED" | string;
  reason: string;
  detail: Record<string, unknown>;
}

export interface TrailingStopSignal {
  trade_id: number;
  should_close: boolean;
  entry_price: number;
  current_price: number;
  move_pct: number;
  threshold_pct: number;
}

export interface CategoryExposure {
  exposure: number;
  ceiling: number | null;
  remaining: number | null;
}

export interface SafetyGateReport {
  allowed: boolean;
  blocks: string[];
  warnings: string[];
  gates: GateStatus[];
  category_exposure: Record<string, CategoryExposure>;
  trailing_stops: TrailingStopSignal[];
}

export interface ApiStatus {
  mode: "paper" | "live" | string;
  live_trading_allowed: boolean;
  daily_pnl: number;
  circuit_breaker: GateStatus;
  time_window: GateStatus;
  active_strategies: string[];
  strategy_flags: StrategyFlags;
  category_exposure: Record<string, CategoryExposure>;
  open_positions: number;
  risk_config: RiskConfig;
  generated_at: string;
}

export interface KellySizingRequest {
  balance: number;
  confidence: number;
  category: string;
  variance?: number;
  odds?: number;
  price?: number;
  k_value?: number;
  max_position_pct?: number;
}

export interface KellySizingResponse {
  suggested_size: number;
  suggested_amount: number;
  f_value: number;
  raw_kelly: number;
  variance_used: number | null;
  capped_by: string | null;
  category: string;
}

export interface Leader {
  id: number;
  address: string;
  win_rate: number;
  sharpe_ratio: number;
  roi: number;
  max_drawdown: number;
  stability_score: number;
  composite_score: number;
  trade_count: number;
  last_updated?: string | null;
}

export interface TradeHistoryItem {
  ts: number;
  market_slug: string;
  category: string;
  side?: string | null;
  price?: number | null;
  size_usd?: number | null;
  pnl_usd?: number | null;
  status: string;
  dry_run: boolean;
  order_id?: string | null;
}

export interface StrategyFlags {
  politics_only: boolean;
  sports_fade: boolean;
  crypto_focus: boolean;
}

export interface StrategiesResponse extends StrategyFlags {
  flags?: StrategyFlags;
  active: string[];
  categories: string[];
}

export interface PlaceOrderRequest {
  market_slug: string;
  token_id: string;
  side: string;
  price: number;
  confidence: number;
  balance: number;
  category?: string;
}

export interface PlaceOrderResponse {
  status: "filled" | "blocked" | "ignored" | "no_fill" | string;
  market_slug: string;
  category: string;
  size_usd: number;
  f_value: number;
  reasons: string[];
  fill: Record<string, unknown> | null;
  trade_id: number | null;
  dry_run: boolean;
}

export interface TradeHistoryParams {
  category?: string;
  start?: string | number;
  end?: string | number;
  status?: string;
  limit?: number;
}

export const riskQueryKeys = {
  all: ["risk-api"] as const,
  status: () => ["risk-api", "status"] as const,
  risk: () => ["risk-api", "risk"] as const,
  gates: (params?: Record<string, unknown>) => ["risk-api", "gates", params] as const,
  sizing: (params: KellySizingRequest) => ["risk-api", "sizing", params] as const,
  leaders: (limit?: number) => ["risk-api", "leaders", limit] as const,
  trades: (params?: TradeHistoryParams) => ["risk-api", "trades", params] as const,
  strategies: () => ["risk-api", "strategies"] as const,
};

export function getApiStatus() {
  return apiFetch<ApiStatus>("/api/status");
}

export function getRiskConfig() {
  return apiFetch<RiskConfig>("/api/risk");
}

export function updateRiskConfig(partial: RiskConfigUpdate) {
  return apiFetch<RiskConfig>("/api/risk/update", {
    method: "POST",
    body: JSON.stringify(partial),
  });
}

export function getRiskGates(
  params: { market_slug?: string; category?: string; size_usd?: number } = {},
) {
  const query = new URLSearchParams();
  if (params.market_slug) query.set("market_slug", params.market_slug);
  if (params.category) query.set("category", params.category);
  if (params.size_usd !== undefined) query.set("size_usd", String(params.size_usd));
  return apiFetch<SafetyGateReport>(`/api/risk/gates${query.size ? `?${query}` : ""}`);
}

export function calculateSizing(request: KellySizingRequest) {
  return apiFetch<KellySizingResponse>("/api/sizing/calculate", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function getLeaders(limit = 50) {
  return apiFetch<Leader[]>(`/api/leaders?limit=${encodeURIComponent(limit)}`);
}

export function refreshLeaders(sync = true) {
  return apiFetch<{ status: string; leaders?: Leader[]; via?: string }>(
    `/api/leaders/refresh?sync=${sync ? "true" : "false"}`,
    { method: "POST" },
  );
}

export function getTradeHistory(params: TradeHistoryParams = {}) {
  const query = new URLSearchParams();
  for (const key of ["category", "status"] as const) {
    if (params[key]) query.set(key, params[key]);
  }
  for (const key of ["start", "end", "limit"] as const) {
    if (params[key] !== undefined) query.set(key, String(params[key]));
  }
  return apiFetch<TradeHistoryItem[]>(`/api/trades/history${query.size ? `?${query}` : ""}`);
}

export function getStrategies() {
  return apiFetch<StrategiesResponse>("/api/strategies");
}

export function updateStrategies(flags: StrategyFlags) {
  return apiFetch<StrategiesResponse>("/api/strategies/update", {
    method: "POST",
    body: JSON.stringify(flags),
  });
}

export function placeOrder(request: PlaceOrderRequest) {
  return apiFetch<PlaceOrderResponse>("/api/trades/place", {
    method: "POST",
    body: JSON.stringify(request),
  });
}

// ------------------------------------------------------------- analytics ----

export interface MetricsSummary {
  system_status: "active" | "paper" | "paused" | string;
  mode: string;
  top_market: string | null;
  current_price: number | null;
  weekly_trades: number;
  weekly_volume: number;
  daily_loss_used: number;
  daily_loss_limit: number;
  daily_pnl_change: number;
  daily_pnl_percent: number;
  closed_today: number;
  open_positions: number;
  generated_at: string;
}

export interface MarketSnapshotRow {
  slug: string;
  category: string;
  price: number | null;
  price_no: number | null;
  ml_signal: "BUY" | "SELL" | "NEUTRAL" | string;
  confidence: number;
  open_pnl: number | null;
  open_positions: number;
  volume_usd: number;
  last_ts: number;
}

export interface FeatureImportanceRow {
  feature: string;
  importance: number;
  shap_value: number;
}

export interface FeatureImportanceResponse {
  status: "ok" | "unavailable" | string;
  model_path: string;
  base_probability?: number;
  features: FeatureImportanceRow[];
  models: string[];
  selected_model: string;
}

export interface VolatilityPoint {
  date: string;
  price: number;
  high: number;
  low: number;
  volatility: number;
  rsi: number | null;
  samples: number;
}

export interface VolatilityResponse {
  market_slug: string;
  category: string;
  days: number;
  points: VolatilityPoint[];
}

export const analyticsQueryKeys = {
  summary: () => ["risk-api", "metrics-summary"] as const,
  snapshot: (category?: string) => ["risk-api", "markets-snapshot", category ?? "all"] as const,
  featureImportance: (model?: string) => ["risk-api", "feature-importance", model ?? "default"] as const,
  volatility: (slug: string, days: number) => ["risk-api", "volatility", slug, days] as const,
  sparklines: (days: number) => ["risk-api", "leader-sparklines", days] as const,
};

export function getMetricsSummary() {
  return apiFetch<MetricsSummary>("/api/metrics/summary");
}

export function getMarketsSnapshot(category?: string) {
  const query = category && category !== "all" ? `?category=${encodeURIComponent(category)}` : "";
  return apiFetch<MarketSnapshotRow[]>(`/api/markets/snapshot${query}`);
}

export function getFeatureImportance(model?: string, topN = 10) {
  const query = new URLSearchParams({ top_n: String(topN) });
  if (model && model !== "default") query.set("model", model);
  return apiFetch<FeatureImportanceResponse>(`/api/analytics/feature_importance?${query}`);
}

export function getVolatility(marketSlug: string, days = 7) {
  return apiFetch<VolatilityResponse>(
    `/api/analytics/volatility/${encodeURIComponent(marketSlug)}?days=${days}`,
  );
}

export function getLeaderSparklines(days = 7) {
  return apiFetch<Record<string, number[]>>(`/api/analytics/leader_sparklines?days=${days}`);
}
